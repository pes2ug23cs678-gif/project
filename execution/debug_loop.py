"""Debug loop — orchestrates Generate → Execute → Fix → Repeat."""

import ast
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from execution.sandbox import sandbox_execute
from agents.debug_expert import fix_code
from config import SANDBOX_MAX_ITER


@dataclass
class IterationRecord:
    iteration:    int
    error_type:   str
    error_detail: str
    fix_applied:  str
    status:       str
    stdout:       str   = ""
    stderr:       str   = ""
    duration:     float = 0.0   # wall-clock seconds for this sandbox run


@dataclass
class DebugResult:
    success:         bool
    final_code:      str
    iterations_used: int
    log:             list = field(default_factory=list)
    error_summary:   Optional[str] = None


# ---------------------------------------------------------------------------
# Static syntax check — no subprocess needed
# ---------------------------------------------------------------------------

def _static_check(code: str) -> tuple:
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError line {e.lineno}: {e.msg}"


# ---------------------------------------------------------------------------
# Error classifier
# ---------------------------------------------------------------------------

def _classify(stderr: str, returncode: int) -> tuple:
    if returncode == 0 and not stderr.strip():
        return "none", ""
    if not stderr.strip():
        return "logic", "non-zero exit with no stderr"
    s = stderr.lower()
    if "syntaxerror" in s or "indentationerror" in s:
        import re
        m = re.search(r'line (\d+)', stderr)
        return "syntax", f"SyntaxError at line {m.group(1)}" if m else "SyntaxError"
    for e in ["NameError","TypeError","ValueError","AttributeError",
              "IndexError","KeyError","FileNotFoundError","IOError",
              "ZeroDivisionError","ImportError","UnboundLocalError"]:
        if e in stderr:
            import re
            m = re.search(r'(\w+Error[^\n]*)', stderr)
            return "runtime", m.group(1) if m else e
    return "runtime", stderr.strip().splitlines()[-1]


# ---------------------------------------------------------------------------
# Rule-based quick fixes (no LLM needed)
# ---------------------------------------------------------------------------

def _quick_fix(code: str, error_type: str, stderr: str) -> tuple:
    """
    Apply fast deterministic fixes for known patterns.
    Returns (new_code, description, was_changed).
    """
    original = code
    fixes = []

    # Fix: zero / spaces figurative constants
    for pattern, replacement in [
        (r'\bif\s+(\w+)\s*==\s*zero\b',  lambda m: f'if {m.group(1)} == 0'),
        (r'\bif\s+(\w+)\s*==\s*spaces\b', lambda m: f'if {m.group(1)}.strip() == ""'),
        (r'\bzero\b',   '0'),
        (r'\bzeros\b',  '0'),
        (r'\bspaces\b', '""'),
        (r'\bspace\b',  '""'),
    ]:
        new = re.sub(pattern, replacement if callable(replacement) else replacement, code)
        if new != code:
            fixes.append("fixed figurative constants")
            code = new

    # Fix: single = in conditions
    for kw in ('if', 'elif', 'while'):
        pattern = rf'\b{kw}\s+(\w+)\s+=\s+([^=\n])'
        new = re.sub(pattern, lambda m: f'{kw} {m.group(1)} == {m.group(2)}', code)
        if new != code:
            fixes.append(f"fixed = → == in {kw} condition")
            code = new

    # Fix: missing decimal import
    if 'Decimal' in code and 'from decimal import' not in code:
        code = 'from decimal import Decimal, InvalidOperation\n' + code
        fixes.append("added missing Decimal import")

    # Fix: missing sys import
    if 'sys.exit' in code and 'import sys' not in code:
        code = 'import sys\n' + code
        fixes.append("added missing sys import")

    # Fix: varying() stub call
    code_new = re.sub(r'[ \t]*varying\(\)[ \t]*\n', '', code)
    code_new = re.sub(r'[ \t]*varying\(\)[ \t]*$', '', code_new, flags=re.MULTILINE)
    if code_new != code:
        fixes.append("removed varying() stub")
        code = code_new

    desc = "; ".join(fixes) if fixes else "no quick fix available"
    return code, desc, code != original


# ---------------------------------------------------------------------------
# Main debug loop
# ---------------------------------------------------------------------------

def run_debug_loop(
    initial_code:   str,
    test_cases:     list = None,
    max_iterations: int  = None,
) -> DebugResult:

    if test_cases is None:
        test_cases = []
    if max_iterations is None:
        max_iterations = SANDBOX_MAX_ITER

    ITERATION_TIMEOUT = 5   # first attempt — full budget
    RETRY_TIMEOUT     = 3   # subsequent attempts — fail fast

    current_code = initial_code
    log = []

    # ── Static pre-check ───────────────────────────────────────────────────
    ok, err = _static_check(current_code)
    if not ok:
        current_code, desc, changed = _quick_fix(current_code, "syntax", err)
        log.append(IterationRecord(0, "syntax", err, desc, "fixed-static"))
        ok, err = _static_check(current_code)
        if not ok:
            # Static fix failed — send to DeepSeek
            current_code = fix_code(current_code, "syntax", err, "")
            ok, err = _static_check(current_code)
            if not ok:
                return DebugResult(False, current_code, 1, log,
                    f"Unrecoverable syntax error: {err}")

    # ── Main loop ──────────────────────────────────────────────────────────
    for iteration in range(1, max_iterations + 1):

        timeout    = ITERATION_TIMEOUT if iteration == 1 else RETRY_TIMEOUT
        t_iter     = time.time()
        result     = sandbox_execute(current_code, timeout=timeout)
        iter_time  = round(time.time() - t_iter, 3)

        stdout      = result["stdout"]
        stderr      = result["stderr"]
        returncode  = result["returncode"]
        error_type, error_detail = _classify(stderr, returncode)

        # Success
        if error_type == "none":
            log.append(IterationRecord(
                iteration, "none", "", "no fix needed", "pass",
                stdout, stderr, iter_time
            ))
            return DebugResult(True, current_code, iteration, log)

        # Try quick rule-based fix first (free, instant)
        fixed_code, fix_desc, changed = _quick_fix(
            current_code, error_type, stderr
        )

        # If quick fix changed nothing, escalate to DeepSeek
        if not changed:
            if error_type == "logic" and not test_cases:
                # Cannot fix logic without oracle — stop cleanly
                log.append(IterationRecord(
                    iteration, "logic", error_detail,
                    "STOPPED — test cases required for logic fix",
                    "fail", stdout, stderr, iter_time
                ))
                return DebugResult(False, current_code, iteration, log,
                    "Logic error: code runs but output is wrong. "
                    "Provide test_cases to enable logic correction.")

            # Send to DeepSeek debug expert
            fix_desc  = f"escalated to DeepSeek: {error_detail[:80]}"
            fixed_code = fix_code(current_code, error_type, stderr, stdout)

        # Stale fix detector — if code unchanged after DeepSeek, give up
        if fixed_code.strip() == current_code.strip():
            log.append(IterationRecord(
                iteration, error_type, error_detail,
                "STOPPED — fix produced identical code", "fail",
                stdout, stderr, iter_time
            ))
            return DebugResult(False, current_code, iteration, log,
                f"Unrecoverable {error_type} error: {error_detail}")

        current_code = fixed_code
        log.append(IterationRecord(
            iteration, error_type, error_detail, fix_desc, "fixed",
            stdout, stderr, iter_time
        ))

    return DebugResult(False, current_code, max_iterations, log,
        f"Exceeded {max_iterations} iterations without success.")
