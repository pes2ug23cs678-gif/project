"""
debug_expert.py — Error diagnosis and fix-suggestion expert.

Receives broken Python code, the associated error message, and the
original COBOL source.  Classifies the error type, analyses root cause,
and builds a structured prompt that an LLM can use to produce corrected
Python code.

Error taxonomy:
  • SyntaxError  — invalid Python syntax
  • NameError    — undefined variable / function
  • TypeError    — wrong type in operation
  • ValueError   — correct type but wrong value
  • RuntimeError — catch-all for execution errors
  • LogicError   — code runs but produces wrong results
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DebugResult:
    """Structured output from the DebugExpert."""

    error_type: str = ""
    error_summary: str = ""
    analysis: str = ""
    fix_suggestions: list[str] = field(default_factory=list)
    corrected_code_prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "error_summary": self.error_summary,
            "analysis": self.analysis,
            "fix_suggestions": self.fix_suggestions,
            "corrected_code_prompt": self.corrected_code_prompt,
        }


class DebugExpert:
    """Diagnoses errors in generated Python and produces fix prompts."""

    # Patterns for common Python error types
    _ERROR_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
        ("SyntaxError",  re.compile(r"SyntaxError:\s*(.+)")),
        ("IndentationError", re.compile(r"IndentationError:\s*(.+)")),
        ("NameError",    re.compile(r"NameError:\s*(.+)")),
        ("TypeError",    re.compile(r"TypeError:\s*(.+)")),
        ("ValueError",   re.compile(r"ValueError:\s*(.+)")),
        ("IndexError",   re.compile(r"IndexError:\s*(.+)")),
        ("KeyError",     re.compile(r"KeyError:\s*(.+)")),
        ("AttributeError", re.compile(r"AttributeError:\s*(.+)")),
        ("ZeroDivisionError", re.compile(r"ZeroDivisionError:\s*(.+)")),
        ("ImportError",  re.compile(r"(?:Import|Module)Error:\s*(.+)")),
        ("RuntimeError", re.compile(r"RuntimeError:\s*(.+)")),
    ]

    # Curated fix-suggestion templates per error type
    _FIX_TEMPLATES: dict[str, list[str]] = {
        "SyntaxError": [
            "Check for missing colons, parentheses, or brackets.",
            "Verify string quotes are properly closed.",
            "Ensure COBOL-to-Python keyword mapping is complete.",
        ],
        "IndentationError": [
            "Verify consistent use of spaces (not tabs).",
            "Check that all blocks are properly indented after if/for/while/def.",
        ],
        "NameError": [
            "Ensure all COBOL data items were translated to Python variables.",
            "Check that paragraph-to-function mappings include all referenced names.",
            "Verify import statements for external modules.",
        ],
        "TypeError": [
            "Check that PIC clauses were mapped to correct Python types.",
            "Ensure Decimal is used for numeric fields with implied decimals.",
            "Verify function signatures match their call sites.",
        ],
        "ValueError": [
            "Check string-to-number conversions from ACCEPT statements.",
            "Verify COMPUTE expressions produce expected value ranges.",
        ],
        "ZeroDivisionError": [
            "Add a guard clause before DIVIDE operations.",
            "Check the divisor variable initialisation matches the COBOL VALUE clause.",
        ],
        "LogicError": [
            "Compare COBOL PERFORM UNTIL loop condition inversion.",
            "Verify EVALUATE/WHEN mapping covers all branches.",
            "Check that COBOL paragraph execution order is preserved.",
        ],
    }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        python_code: str,
        error_message: str,
        cobol_source: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyse an error and produce debugging guidance + fix prompt.

        Parameters
        ----------
        python_code : str
            The Python code that failed.
        error_message : str
            Full error output (traceback or assertion message).
        cobol_source : str, optional
            Original COBOL source for cross-reference.
        context : dict, optional
            RAG-retrieved context.

        Returns
        -------
        dict
            Keys: error_type, error_summary, analysis,
            fix_suggestions, corrected_code_prompt.
        """
        context = context or {}
        result = DebugResult()

        result.error_type, result.error_summary = self._classify_error(error_message)
        result.analysis = self._analyse_error(
            result.error_type, result.error_summary, python_code,
        )
        result.fix_suggestions = self._suggest_fixes(result.error_type)
        result.corrected_code_prompt = self._build_prompt(
            python_code, error_message, cobol_source, result, context,
        )

        return result.to_dict()

    # ------------------------------------------------------------------
    # Error classification
    # ------------------------------------------------------------------

    def _classify_error(self, error_message: str) -> tuple[str, str]:
        """Return (error_type, summary) from the raw error text."""
        for error_type, pattern in self._ERROR_PATTERNS:
            match = pattern.search(error_message)
            if match:
                return error_type, match.group(1).strip()
        # If no pattern matched, treat as generic logic error
        first_line = error_message.strip().splitlines()[0] if error_message.strip() else "Unknown error"
        return "LogicError", first_line

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    @staticmethod
    def _analyse_error(error_type: str, summary: str, code: str) -> str:
        """Build a human-readable analysis of the likely root cause."""
        lines_of_code = code.strip().splitlines()
        code_length = len(lines_of_code)

        analysis_parts = [
            f"Error type : {error_type}",
            f"Summary    : {summary}",
            f"Code size  : {code_length} lines",
        ]

        # Try to extract the offending line number from the summary
        line_match = re.search(r"line (\d+)", summary, re.IGNORECASE)
        if line_match:
            line_no = int(line_match.group(1))
            if 1 <= line_no <= code_length:
                offending = lines_of_code[line_no - 1]
                analysis_parts.append(f"Offending  : L{line_no}: {offending.strip()}")

        if error_type == "NameError":
            name_match = re.search(r"name '(\w+)'", summary)
            if name_match:
                analysis_parts.append(
                    f"Missing name '{name_match.group(1)}' — likely an "
                    "untranslated COBOL data item or paragraph."
                )

        return "\n".join(analysis_parts)

    # ------------------------------------------------------------------
    # Fix suggestions
    # ------------------------------------------------------------------

    def _suggest_fixes(self, error_type: str) -> list[str]:
        """Return curated fix suggestions for the error type."""
        return self._FIX_TEMPLATES.get(error_type, [
            "Review the COBOL source for constructs not yet mapped.",
            "Check variable scope and initialisation.",
            "Compare output against expected COBOL behaviour.",
        ])

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        code: str,
        error: str,
        cobol_source: str,
        result: DebugResult,
        context: dict[str, Any],
    ) -> str:
        """Construct a structured debugging prompt for the LLM."""
        suggestions_md = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(result.fix_suggestions))

        cobol_section = ""
        if cobol_source.strip():
            cobol_section = f"""

## Original COBOL Source
```cobol
{cobol_source.strip()}
```
"""
        rag_section = ""
        if context:
            rag_section = (
                "\n## Retrieved Context (RAG)\n"
                + "\n".join(f"- {k}: {v}" for k, v in context.items())
            )

        return f"""\
You are a Python debugging expert specialising in COBOL-to-Python migrations.

## Task
Fix the Python code below based on the reported error.

## Error Report
- Type   : {result.error_type}
- Message: {result.error_summary}

## Full Error Output
```
{error.strip()}
```

## Faulty Python Code
```python
{code.strip()}
```
{cobol_section}
## Analysis
{result.analysis}

## Suggested Fixes
{suggestions_md}
{rag_section}

## Instructions
1. Identify the root cause of the error.
2. Apply the minimal fix required — do not refactor unrelated code.
3. Preserve the function-per-paragraph structure from the original translation.
4. Return the complete corrected Python file, no explanations.
"""


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    broken_code = """\
import sys
from decimal import Decimal

ws_salary: int = 0
ws_tax: int = 0

def calculate_tax():
    ws_tax = ws_salry * Decimal("0.30")  # typo: ws_salry

def print_result():
    print(f"Tax: {ws_tax}")

def main():
    calculate_tax()
    print_result()

if __name__ == "__main__":
    main()
"""

    error_msg = """\
Traceback (most recent call last):
  File "payroll.py", line 17, in main
    calculate_tax()
  File "payroll.py", line 8, in calculate_tax
    ws_tax = ws_salry * Decimal("0.30")
NameError: name 'ws_salry' is not defined. Did you mean: 'ws_salary'?
"""

    expert = DebugExpert()
    result = expert.run(broken_code, error_msg)
    print(f"Error type : {result['error_type']}")
    print(f"Summary    : {result['error_summary']}")
    print(f"Analysis   :\n{result['analysis']}")
    print(f"Suggestions: {result['fix_suggestions']}")
    print(f"\n--- debugging prompt (first 400 chars) ---")
    print(result["corrected_code_prompt"][:400])
