"""
Diagnostic script for TestExpert — checks all 4 stages:
  1. _derive_cases()     - rule-based test case extraction
  2. _gen_code()         - pytest skeleton generation
  3. _call_llm()         - LLM assertion filling (mocked)
  4. Output structure    - test_cases, test_code, prompt_payload present?
"""
import sys
sys.path.insert(0, "e:/gen_ai/project")

# ── Mock LLM so no real API call is made ───────────────────────────────────
from agents.test_expert import TestExpert
import agents.test_expert as _te

_LLM_CALLED = []
def _mock_llm(prompt, fallback):
    _LLM_CALLED.append(len(prompt))
    # Return a realistic filled test (real assertion, not just 'pass')
    return (
        'import pytest\n'
        'from migrated import *\n\n'
        'class TestAddition:\n'
        '    def test_addition_happy_path(self):\n'
        '        global num1, num2, result\n'
        '        num1, num2, result = 100, 50, 0\n'
        '        addition()\n'
        '        assert result == 150\n'
    )

# Patch the internal LLM method
TestExpert._call_llm = lambda self, prompt, fallback: _mock_llm(prompt, fallback)

# ── Sample data ────────────────────────────────────────────────────────────
SAMPLE_PYTHON = '''
import sys
from decimal import Decimal

num1 = 0
num2 = 0
result = 0
amount_char = ""

def _amount_as_char(value):
    return str(int(value))

def addition():
    global result
    result = num1 + num2

def main():
    global num1, num2
    num1 = 100
    num2 = 50
    addition()
    print(result)

if __name__ == "__main__":
    main()
    sys.exit(0)
'''

SAMPLE_COBOL = """
   IDENTIFICATION DIVISION.
   PROGRAM-ID. PROGRAM-ID.
   DATA DIVISION.
   WORKING-STORAGE SECTION.
   01 NUM1   PIC 9(5) VALUE ZERO.
   01 NUM2   PIC 9(5) VALUE ZERO.
   01 RESULT PIC 9(5) VALUE ZERO.
   PROCEDURE DIVISION.
   ADDITION.
       ADD NUM1 TO NUM2 GIVING RESULT.
       STOP RUN.
"""

SAMPLE_ANALYSIS = {
    "program_id": "PROGRAM-ID",
    "paragraphs": ["addition", "main"],
    "data_items": [
        {"name": "NUM1",   "picture": "9(5)"},
        {"name": "NUM2",   "picture": "9(5)"},
        {"name": "RESULT", "picture": "9(5)"},
    ],
    "has_file_io": False,
    "has_occurs": False,
    "has_redefines": False,
    "line_count": 14,
}

OK  = "[  OK  ]"
ERR = "[ FAIL ]"

print("=" * 62)
print("  TestExpert Diagnostic")
print("=" * 62)

# ── Instantiate ────────────────────────────────────────────────────────────
te = TestExpert()
result = te.run(
    python_code=SAMPLE_PYTHON,
    cobol_source=SAMPLE_COBOL,
    structure_analysis=SAMPLE_ANALYSIS,
)

# ── CHECK 1: Output keys present ───────────────────────────────────────────
print()
print("CHECK 1 — Output dict has required keys")
print("-" * 40)
for key in ("test_cases", "test_code", "prompt_payload"):
    present = key in result and bool(result[key])
    print(f"  {OK if present else ERR}  '{key}' present = {present}")

# ── CHECK 2: Test cases derived ───────────────────────────────────────────
print()
print("CHECK 2 — Test case derivation (rule-based)")
print("-" * 40)
cases = result["test_cases"]
print(f"  Total test cases generated: {len(cases)}")
cats = {}
for tc in cases:
    cats[tc["category"]] = cats.get(tc["category"], 0) + 1
for cat, n in cats.items():
    print(f"  {OK}  {cat}: {n} case(s)")

if not cases:
    print(f"  {ERR}  No test cases derived!")

# Check that paragraph names appear as target functions
print()
print("  Sample test cases:")
for tc in cases[:5]:
    print(f"    name={tc['name']}")
    print(f"      target={tc['target_function']}  category={tc['category']}")
    print(f"      inputs={tc['inputs']}")

# ── CHECK 3: Test code (skeleton) generated ────────────────────────────────
print()
print("CHECK 3 — pytest skeleton / LLM-filled test_code")
print("-" * 40)
test_code = result["test_code"]
has_import   = "import pytest" in test_code or "from" in test_code
has_class    = "class Test" in test_code
has_assert   = "assert" in test_code
has_pass     = "pass" in test_code   # should be GONE if LLM filled correctly

print(f"  {OK if has_import else ERR}  Has import statement:  {has_import}")
print(f"  {OK if has_class  else ERR}  Has test class:        {has_class}")
print(f"  {OK if has_assert else ERR}  Has assert statement:  {has_assert}")
print(f"  {'[ WARN]' if has_pass else OK}  Has stub 'pass':       {has_pass}  (should be False after LLM fill)")
print(f"  LLM was called: {bool(_LLM_CALLED)}  (prompt chars={_LLM_CALLED[0] if _LLM_CALLED else 0})")

# ── CHECK 4: Prompt payload non-empty ──────────────────────────────────────
print()
print("CHECK 4 — Prompt payload sent to LLM")
print("-" * 40)
payload = result["prompt_payload"]
has_cobol  = "ADDITION" in payload.upper()  or "COBOL" in payload.upper()
has_python = "def addition" in payload or "def main" in payload
has_cases  = "happy_path" in payload or "boundary" in payload
print(f"  {OK if has_cobol  else ERR}  Contains COBOL context:   {has_cobol}")
print(f"  {OK if has_python else ERR}  Contains Python code:     {has_python}")
print(f"  {OK if has_cases  else ERR}  Contains test case list:  {has_cases}")
print(f"  Payload length: {len(payload)} chars")

# ── CHECK 5: Boundary cases from data_items ────────────────────────────────
print()
print("CHECK 5 — Boundary cases from PIC clauses")
print("-" * 40)
boundary = [tc for tc in cases if tc["category"] == "boundary"]
print(f"  Boundary cases found: {len(boundary)}")
for tc in boundary:
    print(f"    {tc['name']}  inputs={tc['inputs']}")
expected_min = any(tc["inputs"].get("num1") == 0 for tc in boundary)
expected_max = any(tc["inputs"].get("num1") == 99999 for tc in boundary)
print(f"  {OK if expected_min else ERR}  Min boundary (0) derived:     {expected_min}")
print(f"  {OK if expected_max else ERR}  Max boundary (99999) derived: {expected_max}")

# ── CHECK 6: Generated test_code parseable as Python ─────────────────────
print()
print("CHECK 6 — test_code is valid Python (ast.parse)")
print("-" * 40)
import ast
try:
    ast.parse(test_code)
    print(f"  {OK}  test_code passes ast.parse()")
except SyntaxError as e:
    print(f"  {ERR}  SyntaxError in generated test_code: {e}")

# ── Full test_code preview ─────────────────────────────────────────────────
print()
print("CHECK 7 — test_code preview (first 30 lines)")
print("-" * 40)
for i, line in enumerate(test_code.splitlines()[:30], 1):
    print(f"  {i:3d} | {line}")

print()
print("=" * 62)
print("  DIAGNOSTIC COMPLETE")
print("=" * 62)
