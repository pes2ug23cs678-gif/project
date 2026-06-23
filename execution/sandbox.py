"""Sandbox — safe subprocess execution. No LLM involved."""

import os
import re
import sys
import shutil
import tempfile
import subprocess


def _detect_file_refs(code: str) -> list[str]:
    """Extract all file path references from the generated Python code."""
    refs = set()
    # Matches: SOME_PATH = "filename.ext" or SOME_PATH = 'filename.ext'
    for m in re.finditer(r"""[=\(]\s*["']([^"']+\.(?:dat|txt|csv|log|out|rpt))["']""", code):
        refs.add(m.group(1))
    # Also match: open("filename.ext")
    for m in re.finditer(r"""open\s*\(\s*["']([^"']+)["']""", code):
        refs.add(m.group(1))
    # Also match: FILE_PATH constants
    for m in re.finditer(r"""^\w+_(?:FILE_)?PATH\s*=\s*["']([^"']+)["']""", code, re.MULTILINE):
        refs.add(m.group(1))
    return list(refs)


def _extract_field_slices(code: str) -> dict:
    """Parse _parse_*_line functions to extract field positions.
    
    Returns a dict mapping function keywords (e.g. 'account', 'transaction')
    to a list of (start, end, field_name, is_numeric) tuples.
    """
    result = {}
    # Find all _parse_*_line functions
    for fn_match in re.finditer(r'def\s+_parse_(\w+)_line\s*\(', code):
        keyword = fn_match.group(1).lower()
        fn_start = fn_match.start()
        # Find end of function (next def or end of code)
        next_def = code.find('\ndef ', fn_start + 1)
        fn_body = code[fn_start:next_def] if next_def > 0 else code[fn_start:]
        
        fields = []
        seen_slices = set()
        
        for line_text in fn_body.splitlines():
            # Find all line[X:Y] on this line
            for slice_m in re.finditer(r'line\[(\d+):(\d+)\]', line_text):
                start_pos = int(slice_m.group(1))
                end_pos = int(slice_m.group(2))
                
                if (start_pos, end_pos) in seen_slices:
                    continue
                seen_slices.add((start_pos, end_pos))
                
                # Extract field name: look for "field_name": or ["field_name"] on this line
                name = f"field_{start_pos}_{end_pos}"
                key_m = re.search(r'["\'](\w+)["\']\s*[\]:]', line_text)
                if key_m:
                    name = key_m.group(1)
                
                # Detect if numeric: int(), Decimal(), float() on same line
                is_numeric = bool(re.search(r'\b(?:int|Decimal|float)\s*\(', line_text))
                
                fields.append((start_pos, end_pos, name, is_numeric))
        
        if fields:
            # Sort by start position
            fields.sort(key=lambda x: x[0])
            result[keyword] = fields
    
    return result


def _generate_stub_line(fields: list) -> str:
    """Generate a perfectly aligned stub record from extracted field slices."""
    if not fields:
        return " " * 80 + "\n"
    
    # Find total record width
    max_end = max(end for _, end, _, *_ in fields)
    record = [' '] * max_end
    
    for field_tuple in fields:
        start, end, field_name = field_tuple[0], field_tuple[1], field_tuple[2]
        is_numeric = field_tuple[3] if len(field_tuple) > 3 else False
        width = end - start
        fn_lower = field_name.lower()
        
        # Generate appropriate test data based on field name
        # NOTE: Order matters! More specific checks come first.
        if any(x in fn_lower for x in ['date']):
            value = "20250101"[:width].ljust(width, '0')
        elif any(x in fn_lower for x in ['id', 'num', 'number']):
            value = "000001".rjust(width, '0')[-width:]
        elif any(x in fn_lower for x in ['name']):
            value = "Test Record".ljust(width)[:width]
        elif any(x in fn_lower for x in ['balance', 'amount', 'pay', 'salary', 'price', 'total', 'gross', 'net', 'tax']):
            # Numeric with decimals — format to exact field width
            if width >= 9:
                value = f"{1000.00:0{width}.2f}"[-width:]
            elif width >= 6:
                value = f"{100.00:0{width}.2f}"[-width:]
            else:
                value = "0" * width
        elif any(x in fn_lower for x in ['type', 'status', 'grade', 'code']):
            if width == 1:
                value = "D"  # common transaction type
            elif width == 2:
                value = "03"
            else:
                value = "A".ljust(width)[:width]
        elif any(x in fn_lower for x in ['dept', 'department']):
            value = "SALES".ljust(width)[:width]
        elif any(x in fn_lower for x in ['eof', 'flag']):
            value = "N".ljust(width)[:width]
        elif is_numeric:
            # Detected as numeric from code context — use safe integer
            value = "0".rjust(width, '0')
        else:
            # Default: spaces (string field)
            value = " " * width
        
        for i, ch in enumerate(value[:width]):
            record[start + i] = ch
    
    return "".join(record) + "\n"


def _generate_stub_data(fname: str, code: str) -> str:
    """Generate smart stub data based on code analysis of parse functions."""
    name_lower = fname.lower()
    
    # First try: use parsed field slices from the actual code
    field_map = _extract_field_slices(code)
    
    for keyword, fields in field_map.items():
        # Match file name to parse function keyword
        if keyword in name_lower or name_lower.replace('.dat', '').replace('.txt', '') in keyword:
            return _generate_stub_line(fields)
    
    # Second try: if there's only one parse function, use it for input files
    if len(field_map) == 1 and any(x in name_lower for x in ['input', 'in', 'read']):
        only_fields = list(field_map.values())[0]
        return _generate_stub_line(only_fields)
    
    # Fallback for output/report files — just create empty
    if any(x in name_lower for x in ['report', 'output', 'rpt', 'out', 'log', 'error']):
        return ""
    
    # Generic fallback: detect max slice width from ALL parse functions
    all_fields = []
    for fields in field_map.values():
        all_fields.extend(fields)
    
    if all_fields:
        max_width = max(end for _, end, *_ in all_fields)
        return " " * max_width + "\n"
    
    # Last resort
    return " " * 80 + "\n"


def sandbox_execute(code: str, timeout: int = 5) -> dict:
    """
    Write code to a temp directory, create stub data files,
    run with subprocess, return results.
    Never uses exec() or eval().
    """
    tmp_dir = tempfile.mkdtemp()
    try:
        # Detect all file path string constants in the code
        file_refs = _detect_file_refs(code)

        # Create stub files so open() does not crash
        for fname in file_refs:
            fpath = os.path.join(tmp_dir, os.path.basename(fname))
            if not os.path.exists(fpath):
                stub_data = _generate_stub_data(fname, code)
                with open(fpath, "w") as f:
                    f.write(stub_data)

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
    verbose stdout, and returns a structured result dict.
    """
    tmp_dir = tempfile.mkdtemp()
    try:
        # Write the translated module so the test file can import it
        module_path = os.path.join(tmp_dir, f"{module_name}.py")
        with open(module_path, "w", encoding="utf-8") as fh:
            fh.write(module_code)

        # Also create stub data files for the module (tests may import and run it)
        file_refs = _detect_file_refs(module_code)
        for fname in file_refs:
            fpath = os.path.join(tmp_dir, os.path.basename(fname))
            if not os.path.exists(fpath):
                stub_data = _generate_stub_data(fname, module_code)
                with open(fpath, "w") as f:
                    f.write(stub_data)

        # Write the generated pytest test file
        test_path = os.path.join(tmp_dir, f"test_{module_name}.py")
        with open(test_path, "w", encoding="utf-8") as fh:
            fh.write(test_code)

        # Write a conftest.py that redirects stdin to prevent interactive hangs
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

        # Also capture collection errors from stderr
        if result.returncode == 2 and not errors:
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
