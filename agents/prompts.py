"""Prompt templates for all expert modules.

Each class exposes a single ``build(...)`` class method that returns the
rendered prompt string.  Business logic stays in the expert modules;
presentation and LLM instruction design lives here.
"""

from __future__ import annotations

from typing import Any


# ===================================================================
# Structure Expert prompt
# ===================================================================

class StructurePrompt:
    """Prompt builder for the COBOL structure-analysis expert."""

    @classmethod
    def build(
        cls,
        source: str,
        program_id: str,
        divisions: list[str],
        paragraphs: list[str],
        paragraph_details: list[dict[str, Any]],
        data_items: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> str:
        rag = cls._rag_section(context)
        para_bodies = cls._para_bodies(paragraph_details)

        return f"""\
You are a COBOL structure analysis expert.

## Task
Analyse the following COBOL program and verify / enrich the structural
breakdown provided below.

## COBOL Source
```cobol
{source.strip()}
```

## Preliminary Analysis
- Program ID: {program_id}
- Divisions : {', '.join(divisions)}
- Paragraphs: {', '.join(paragraphs) or 'none'}
- Data items: {len(data_items)}
{para_bodies}
{rag}

## Instructions
1. Confirm or correct the division/section/paragraph identification.
2. Describe the logical flow of the PROCEDURE DIVISION step-by-step.
3. Note any COPY or CALL dependencies.
4. Identify level-88 condition names and REDEFINES relationships.
5. Return your answer as structured JSON with keys:
   divisions, sections, paragraphs, paragraph_bodies, data_items, logical_flow.
"""

    @staticmethod
    def _rag_section(context: dict[str, Any]) -> str:
        if not context:
            return ""
        lines = "\n".join(f"- {k}: {v}" for k, v in context.items())
        return f"\n## Retrieved Context\n{lines}"

    @staticmethod
    def _para_bodies(details: list[dict[str, Any]]) -> str:
        if not details:
            return ""
        parts = []
        for pd in details:
            body = "\n".join(f"    {ln}" for ln in pd.get("body", []))
            parts.append(f"  {pd['name']}:\n{body}")
        return "\n## Paragraph Bodies\n" + "\n".join(parts)


# ===================================================================
# Translation Expert prompt
# ===================================================================

class TranslationPrompt:
    """Prompt builder for the COBOL-to-Python translation expert."""

    @classmethod
    def build(
        cls,
        source: str,
        analysis: dict[str, Any],
        python_skeleton: str,
        mapping_table: list[dict[str, str]],
        context: dict[str, Any],
    ) -> str:
        mapping_md = "\n".join(
            f"| {m['cobol']} | {m['python']} | {m['notes']} |"
            for m in mapping_table
        )
        rag = cls._rag_section(context)

        return f"""\
You are a COBOL-to-Python translation expert.

## Task
Translate the COBOL program below into clean, idiomatic Python 3.10+.

## COBOL Source
```cobol
{source.strip()}
```

## Structural Analysis
- Program ID : {analysis.get('program_id', 'UNKNOWN')}
- Divisions  : {', '.join(analysis.get('divisions', []))}
- Paragraphs : {', '.join(analysis.get('paragraphs', []))}
- Data items : {len(analysis.get('data_items', []))}

## Construct Mapping Reference
| COBOL | Python | Notes |
|-------|--------|-------|
{mapping_md}

## Python Skeleton (auto-generated, may need refinement)
```python
{python_skeleton}
```
{rag}

## Chain-of-Thought Instructions
Follow these steps IN ORDER before writing any code:

1. **List every COBOL statement** in the PROCEDURE DIVISION.
2. **Map each statement** to its Python equivalent using the table above.
3. **Identify data types**: for each data item, determine the Python type
   from the PIC clause (9→int, 9V9→Decimal, A/X→str, 88→bool).
4. **Handle scope**: any function that reads or modifies a module-level
   variable must include a `global` declaration.
5. **Translate control flow**:
   - PERFORM paragraph → function call
   - PERFORM UNTIL → while not …
   - EVALUATE/WHEN → match/case
   - IF/ELSE → if/else
6. **Assemble the final Python file**, one function per COBOL paragraph.

## Few-Shot Example

### Input COBOL
```cobol
IDENTIFICATION DIVISION.
PROGRAM-ID. GREETING.
DATA DIVISION.
WORKING-STORAGE SECTION.
01 WS-NAME PIC A(20).
PROCEDURE DIVISION.
    ACCEPT WS-NAME.
    DISPLAY 'HELLO, ' WS-NAME.
    STOP RUN.
```

### Expected Python Output
```python
import sys

ws_name: str = ""

def main():
    global ws_name
    ws_name = input("Enter name: ")
    print(f"HELLO, {{ws_name}}")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

## Final Instructions
1. Complete or fix the auto-generated skeleton above.
2. Preserve the function-per-paragraph structure.
3. Use `Decimal` for numeric fields with implied decimals (PIC 9(n)V99).
4. Handle COBOL-specific idioms:
   - Level-88 items → boolean properties or constants.
   - REDEFINES → `@property` providing alternate view.
   - COPY books → import statements.
5. Add type hints and docstrings.
6. Return ONLY the complete Python file content, no explanations.
"""

    @staticmethod
    def _rag_section(context: dict[str, Any]) -> str:
        if not context:
            return ""
        lines = "\n".join(f"- {k}: {v}" for k, v in context.items())
        return f"\n## Retrieved Context (RAG)\n{lines}"


# ===================================================================
# Debug Expert prompt
# ===================================================================

class DebugPrompt:
    """Prompt builder for the debugging expert."""

    @classmethod
    def build(
        cls,
        code: str,
        error: str,
        cobol_source: str,
        error_type: str,
        error_summary: str,
        severity: int,
        root_cause: str,
        analysis: str,
        fix_suggestions: list[str],
        traceback_frames: list[dict[str, Any]],
        offending_lines: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> str:
        suggestions_md = "\n".join(
            f"  {i + 1}. {s}" for i, s in enumerate(fix_suggestions)
        )
        offending_md = cls._offending_section(offending_lines)
        frames_md = cls._frames_section(traceback_frames)
        cobol_section = cls._cobol_section(cobol_source)
        rag = cls._rag_section(context)
        sev_label = (
            "Trivial fix" if severity <= 2
            else "Moderate complexity" if severity <= 3
            else "Complex — requires careful analysis"
        )

        return f"""\
You are a senior Python engineer specialising in debugging COBOL-to-Python
migration code. You have deep knowledge of both COBOL semantics and Python
best practices.

## Severity
{severity}/5 — {sev_label}

## Error Report
- **Type**    : `{error_type}`
- **Message** : `{error_summary}`

## Call Stack ({len(traceback_frames)} frames)
{frames_md or "  No traceback frames available."}

## Full Traceback
```
{error.strip()}
```

## Offending Code (with context)
{offending_md or "  Unable to pinpoint offending lines."}

## Complete Source Code
```python
{code.strip()}
```
{cobol_section}
## Root Cause Analysis
{root_cause}

## Detailed Analysis
{analysis}

## Suggested Fixes
{suggestions_md}
{rag}

## Chain-of-Thought Debugging Instructions
Follow these steps IN ORDER:

1. **READ** the error message and traceback carefully.
2. **LOCATE** the exact line(s) in the Python code that caused the error.
3. **CROSS-REFERENCE** with the original COBOL source to understand the
   intended behaviour.
4. **IDENTIFY** whether this is a translation error (wrong mapping),
   a scope error (missing global), a type error (wrong PIC mapping),
   or a logic error (wrong control flow).
5. **APPLY** the minimal fix — do NOT refactor unrelated code.
6. **VERIFY** mentally that the fix preserves the original COBOL semantics.

## Few-Shot Example

### Error
```
NameError: name 'ws_salry' is not defined. Did you mean: 'ws_salary'?
```

### Fix
Change `ws_salry` to `ws_salary` on the offending line. This was a typo
introduced during COBOL-to-Python name translation.

```diff
- ws_tax = ws_salry * Decimal("0.30")
+ ws_tax = ws_salary * Decimal("0.30")
```

## Output Format
Return your response in this EXACT format:

### Explanation
[1-2 sentence explanation of what went wrong and why]

### Corrected Code
```python
[Complete corrected Python file — not just the changed lines]
```
"""

    @staticmethod
    def _cobol_section(source: str) -> str:
        if not source.strip():
            return ""
        return f"""
## Original COBOL Source
```cobol
{source.strip()}
```
"""

    @staticmethod
    def _rag_section(context: dict[str, Any]) -> str:
        if not context:
            return ""
        lines = "\n".join(f"- {k}: {v}" for k, v in context.items())
        return f"\n## Retrieved Context (RAG)\n{lines}"

    @staticmethod
    def _offending_section(offending: list[dict[str, Any]]) -> str:
        if not offending:
            return ""
        parts = []
        for ol in offending:
            ctx = "\n".join(ol["context"])
            parts.append(f"**Line {ol['line_number']}:**\n```\n{ctx}\n```")
        return "\n".join(parts)

    @staticmethod
    def _frames_section(frames: list[dict[str, Any]]) -> str:
        if not frames:
            return ""
        return "\n".join(
            f"  {i + 1}. `{f['function']}()` at line {f['line']}: `{f['code']}`"
            for i, f in enumerate(frames)
        )


# ===================================================================
# Test Expert prompt
# ===================================================================

class TestPrompt:
    """Prompt builder for the test-generation expert."""

    @classmethod
    def build(
        cls,
        python_code: str,
        cobol_source: str,
        test_cases_summary: str,
        test_skeleton: str,
        context: dict[str, Any],
    ) -> str:
        cobol_section = cls._cobol_section(cobol_source)
        rag = cls._rag_section(context)

        return f"""\
You are a senior QA engineer specialising in COBOL-to-Python migration
testing. You write thorough, deterministic pytest test suites that verify
both functional correctness and COBOL-semantic equivalence.

## Task
Complete the pytest test suite below so every test case has meaningful,
deterministic assertions that verify the translated Python code is
functionally equivalent to the original COBOL program.

## Python Code Under Test
```python
{python_code.strip()}
```
{cobol_section}
## Test Scenarios
{test_cases_summary}

## Test Skeleton
```python
{test_skeleton}
```
{rag}

## Chain-of-Thought Instructions
Follow these steps IN ORDER:

1. **READ** each COBOL paragraph and understand what it computes.
2. **DERIVE** the expected output for each test scenario by manually
   tracing through the COBOL logic with the given inputs.
3. **CHOOSE** the right assertion pattern for each test category:
   - `happy_path`  → `assert function() == expected_value`
   - `boundary`    → `assert function(min_val)` and `assert function(max_val)`
   - `type_check`  → `assert isinstance(var, expected_type)`
   - `error`       → `with pytest.raises(ExpectedException):`
4. **WRITE** the assertions, replacing every `pass` stub.
5. **VERIFY** that each test is self-contained and does not depend on
   execution order.

## Few-Shot Example

### COBOL Logic
```cobol
COMPUTE WS-TAX = WS-SALARY * 0.30.
```

### Corresponding Test
```python
class TestCalculateTax:
    def test_calculate_tax_happy_path(self):
        \"\"\"Verify tax is 30% of salary.\"\"\"
        import payroll
        payroll.ws_salary = Decimal("1000")
        payroll.calculate_tax()
        assert payroll.ws_tax == Decimal("300.00"), (
            f"Expected 300.00, got {{payroll.ws_tax}}"
        )

    def test_calculate_tax_zero_salary(self):
        \"\"\"Boundary: zero salary should produce zero tax.\"\"\"
        import payroll
        payroll.ws_salary = Decimal("0")
        payroll.calculate_tax()
        assert payroll.ws_tax == Decimal("0")
```

## Output Format
Return ONLY the complete pytest file. Do not include explanations
outside the code block. Every test must have at least one `assert`
statement or a `pytest.raises` context manager.

```python
[complete test file here]
```
"""

    @staticmethod
    def _cobol_section(source: str) -> str:
        if not source.strip():
            return ""
        return f"""
## Original COBOL Source (reference for deriving expected values)
```cobol
{source.strip()}
```
"""

    @staticmethod
    def _rag_section(context: dict[str, Any]) -> str:
        if not context:
            return ""
        lines = "\n".join(f"- {k}: {v}" for k, v in context.items())
        return f"\n## Retrieved Context (RAG)\n{lines}"
