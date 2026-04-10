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
