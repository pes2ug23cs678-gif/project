"""Sandbox — safe subprocess execution. No LLM involved."""

import os
import re
import sys
import shutil
import tempfile
import subprocess


def sandbox_execute(code: str, timeout: int = 5) -> dict:
    """
    Write code to a temp directory, create stub data files,
    run with subprocess, return results.
    Never uses exec() or eval().
    """
    tmp_dir = tempfile.mkdtemp()
    try:
        # Detect all file path string constants in the code
        # Matches: SOME_PATH = "filename.dat" or open("filename.dat")
        file_refs = re.findall(
            r'[=\(]\s*["\']([^"\']+\.(?:dat|txt|csv|log))["\']',
            code
        )
        file_refs = list(set(file_refs))

        # Create stub files so open() does not crash
        for fname in file_refs:
            fpath = os.path.join(tmp_dir, os.path.basename(fname))
            if not os.path.exists(fpath):
                name_lower = fname.lower()
                if "account" in name_lower:
                    with open(fpath, "w") as f:
                        f.write("000001Test Account               S 000001000.00A\n")
                        f.write("000002Second Account             C 000002500.50A\n")
                elif "transaction" in name_lower:
                    with open(fpath, "w") as f:
                        f.write("000001D 000010000020250101\n")
                        f.write("000002W 000005000020250101\n")
                elif any(x in name_lower for x in ["error", "log"]):
                    open(fpath, "w").close()   # writable empty file
                elif any(x in name_lower for x in ["report", "output"]):
                    open(fpath, "w").close()   # writable empty file
                else:
                    open(fpath, "w").close()   # generic empty stub

        # Write the generated Python into the temp dir
        tmp_path = os.path.join(tmp_dir, "migrated.py")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(code)

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tmp_dir       # ← run from temp dir so relative paths resolve
        )

        return {
            "returncode": result.returncode,
            "stdout":     result.stdout,
            "stderr":     result.stderr,
        }

    except subprocess.TimeoutExpired:
        return {
            "returncode": -1,
            "stdout":     "",
            "stderr":     "TimeoutExpired: program ran longer than "
                          f"{timeout}s — likely infinite loop"
        }
    except Exception as exc:
        return {"returncode": -1, "stdout": "", "stderr": str(exc)}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def sandbox_pytest(module_code: str, test_code: str, module_name: str = "migrated",
                   timeout: int = 30, maxfail: int = None) -> dict:
    """
    Run a pytest suite safely inside a subprocess sandbox.

    Writes the translated Python module and the generated pytest file to a
    temp directory, executes ``python -m pytest --tb=short -v``, parses the
    verbose stdout, and returns a structured result dict:

    Returns
    -------
    dict with keys:
        passed  – list of test node-ids that passed
        failed  – list of test node-ids that failed / errored
        errors  – list of collection/import errors (strings)
        summary – human-readable one-liner (e.g. "3 passed, 1 failed")
        stdout  – raw pytest stdout
        stderr  – raw pytest stderr
        returncode – pytest exit code (0 = all pass, 1 = some fail, 5 = no tests)
    """
    tmp_dir = tempfile.mkdtemp()
    try:
        # Write the translated module so the test file can import it
        module_path = os.path.join(tmp_dir, f"{module_name}.py")
        with open(module_path, "w", encoding="utf-8") as fh:
            fh.write(module_code)

        # Write the generated pytest test file
        test_path = os.path.join(tmp_dir, f"test_{module_name}.py")
        with open(test_path, "w", encoding="utf-8") as fh:
            fh.write(test_code)

        # Write a conftest.py that redirects stdin to prevent interactive hangs
        # when the imported module calls input() at module level
        conftest_path = os.path.join(tmp_dir, "conftest.py")
        with open(conftest_path, "w", encoding="utf-8") as fh:
            fh.write(
                "import sys, io\n"
                "sys.stdin = io.StringIO('')  # prevent input() hangs during import\n"
            )

        cmd = [sys.executable, "-m", "pytest", f"test_{module_name}.py",
               "--tb=short", "-v", "--no-header"]
        if maxfail is not None:
            cmd.append(f"--maxfail={str(maxfail)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tmp_dir,
        )

        # ── Detect pytest not installed ────────────────────────────────
        if "No module named pytest" in result.stderr:
            return {
                "passed": [], "failed": [], "errors": ["pytest not installed"],
                "summary": "Error: pytest not installed in this environment",
                "stdout": result.stdout, "stderr": result.stderr,
                "returncode": result.returncode,
            }

        # ── Parse verbose pytest output ────────────────────────────────
        passed, failed, errors = [], [], []
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if " PASSED" in stripped:
                node = stripped.split(" PASSED")[0].strip()
                passed.append(node)
            elif " FAILED" in stripped:
                node = stripped.split(" FAILED")[0].strip()
                failed.append(node)
            elif stripped.startswith("ERROR ") or "ERROR collecting" in stripped:
                errors.append(stripped)

        # Also capture collection errors from stderr (import failures etc.)
        if result.returncode == 2 and not errors:
            # returncode 2 = interrupted / collection error
            for line in (result.stdout + result.stderr).splitlines():
                if any(kw in line for kw in ["ImportError", "ModuleNotFoundError",
                                              "SyntaxError", "NameError", "ERROR"]):
                    errors.append(line.strip())
                    break

        total = len(passed) + len(failed)
        if total == 0 and result.returncode == 5:
            summary = "No tests collected (collection may have failed)"
        elif total == 0 and errors:
            summary = f"Collection error: {errors[0][:80]}"
        else:
            parts = []
            if passed:
                parts.append(f"{len(passed)} passed")
            if failed:
                parts.append(f"{len(failed)} failed")
            if errors:
                parts.append(f"{len(errors)} error(s)")
            summary = ", ".join(parts) if parts else "0 tests"

        return {
            "passed":     passed,
            "failed":     failed,
            "errors":     errors,
            "summary":    summary,
            "stdout":     result.stdout,
            "stderr":     result.stderr,
            "returncode": result.returncode,
        }

    except subprocess.TimeoutExpired:
        return {
            "passed": [], "failed": [], "errors": [],
            "summary": f"TimeoutExpired after {timeout}s",
            "stdout": "", "stderr": f"TimeoutExpired: pytest ran longer than {timeout}s",
            "returncode": -1,
        }
    except Exception as exc:
        return {
            "passed": [], "failed": [], "errors": [],
            "summary": f"Exception: {exc}",
            "stdout": "", "stderr": str(exc),
            "returncode": -1,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
