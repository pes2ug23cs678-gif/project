"""Diagnostic script — verifies the debug loop catches all 5 error categories."""
import sys
sys.path.insert(0, "e:/gen_ai/project")

# ── Monkey-patch fix_code so no real LLM API call is made ──────────────────
import agents.debug_expert as _de
def _mock_fix(code, etype, stderr, stdout):
    print(f"    [LLM CALLED] error_type={etype}  stderr={stderr[:80]!r}")
    return code  # return same code → triggers stale-fix detector → clean exit
_de.fix_code = _mock_fix

import execution.debug_loop as _dl
_dl.fix_code = _mock_fix

from execution.debug_loop import run_debug_loop

PASS = "\033[92m PASS \033[0m"
FAIL = "\033[91m FAIL \033[0m"

def banner(title):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)

def show(r):
    for rec in r.log:
        print(f"  [{rec.iteration}] {rec.error_type:10} | {rec.status:14} | {rec.fix_applied[:52]}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
banner("TEST 1 — SyntaxError: caught by ast.parse pre-check?")
code1 = "def foo(\n    print('hello')\n"
r1 = run_debug_loop(code1, max_iterations=2)
show(r1)
caught = any(rec.error_type == "syntax" for rec in r1.log)
print(f"  → SyntaxError caught: {PASS if caught else FAIL}  (success={r1.success})")
print(f"     summary: {r1.error_summary}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
banner("TEST 2 — RuntimeError (NameError): classified + LLM escalated?")
code2 = (
    "import sys\n"
    "def main():\n"
    "    print(undefined_var)\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
    "    sys.exit(0)\n"
)
r2 = run_debug_loop(code2, max_iterations=2)
show(r2)
caught2 = any(rec.error_type == "runtime" for rec in r2.log)
print(f"  → RuntimeError caught:  {PASS if caught2 else FAIL}  (success={r2.success})")
print(f"     summary: {r2.error_summary}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
banner("TEST 3 — Clean code: passes on iteration 1 with no fix?")
code3 = (
    "import sys\n"
    "def main():\n"
    "    print(42)\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
    "    sys.exit(0)\n"
)
r3 = run_debug_loop(code3, max_iterations=3)
show(r3)
clean_pass = r3.success and r3.iterations_used == 1
print(f"  → Passed in 1 iteration: {PASS if clean_pass else FAIL}  (success={r3.success}, iter={r3.iterations_used})")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
banner("TEST 4 — Figurative constant bug: caught by rule-based quick-fix?")
code4 = (
    "import sys\n"
    "ws_eof = 'N'\n"
    "def main():\n"
    "    if ws_eof == spaces:\n"
    "        print('empty')\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
    "    sys.exit(0)\n"
)
r4 = run_debug_loop(code4, max_iterations=3)
show(r4)
rule_fixed = r4.success
print(f"  → Rule-based fix worked: {PASS if rule_fixed else FAIL}  (success={r4.success}, iter={r4.iterations_used})")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
banner("TEST 5 — Logic error (wrong output): stops cleanly without test_code?")
code5 = (
    "import sys\n"
    "def add(a, b):\n"
    "    return a - b   # BUG: should be +\n"
    "if __name__ == '__main__':\n"
    "    print(add(2, 3))\n"
    "    sys.exit(0)\n"
)
r5 = run_debug_loop(code5, max_iterations=2, test_cases=[])
show(r5)
clean_stop = not r5.success  # should NOT report success: logic is wrong
# Without test_code it runs cleanly so it will report success=True (expected limitation)
print(f"  → Logic error (no test_code): success={r5.success}")
print(f"     (Expected: True — sans pytest, crash-free = 'pass'. Limitation confirmed.)")
print(f"     summary: {r5.error_summary}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
banner("TEST 6 — Logic error WITH test_code: caught and LLM escalated?")
code6 = (
    "import sys\n"
    "def add(a, b):\n"
    "    return a - b   # BUG\n"
    "if __name__ == '__main__':\n"
    "    print(add(2, 3))\n"
    "    sys.exit(0)\n"
)
test_code6 = (
    "from migrated import add\n"
    "def test_add():\n"
    "    assert add(2, 3) == 5, f'Expected 5, got {add(2,3)}'\n"
)
r6 = run_debug_loop(code6, max_iterations=2, test_code=test_code6, module_name="migrated")
show(r6)
logic_caught = any(rec.error_type == "logic" for rec in r6.log)
print(f"  → Logic error caught via pytest: {PASS if logic_caught else FAIL}  (success={r6.success})")
print(f"     summary: {r6.error_summary}")

print()
print("=" * 60)
print("  DIAGNOSTIC COMPLETE")
print("=" * 60)
