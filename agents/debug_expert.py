"""
debug_expert.py — Intelligent error diagnosis and fix-generation expert.

Receives broken Python code, the associated error/traceback, and the
original COBOL source.  Performs deep analysis:

  1. **Error classification** — 13 Python exception types + LogicError
  2. **Traceback parsing** — extracts file, line, function, and code
     from every frame in the traceback
  3. **Root-cause analysis** — cross-references the error against the
     COBOL source to identify mistranslation patterns
  4. **Severity scoring** — rates the fix difficulty (1-5)
  5. **Context-aware fix suggestions** — dynamic suggestions based on
     the actual error content, not just the error type
  6. **Diff-oriented prompt** — asks the LLM to return both the fix
     explanation and corrected code

Error taxonomy:
  • SyntaxError       — invalid Python syntax
  • IndentationError  — whitespace issues
  • NameError         — undefined variable / function
  • TypeError         — wrong type in operation
  • ValueError        — correct type, wrong value
  • IndexError        — list/tuple index out of range
  • KeyError          — missing dict key
  • AttributeError    — missing attribute on object
  • ZeroDivisionError — division by zero
  • ImportError       — missing module
  • RuntimeError      — catch-all execution error
  • FileNotFoundError — missing file (COBOL file I/O)
  • OverflowError     — numeric overflow (PIC size exceeded)
  • LogicError        — code runs but produces wrong results
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TracebackFrame:
    """A single frame extracted from a Python traceback."""

    filename: str = ""
    line_number: int = 0
    function_name: str = ""
    code_line: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.filename,
            "line": self.line_number,
            "function": self.function_name,
            "code": self.code_line,
        }


@dataclass
class DebugResult:
    """Structured output from the DebugExpert."""

    error_type: str = ""
    error_summary: str = ""
    severity: int = 1                                  # 1 (trivial) → 5 (critical)
    traceback_frames: list[TracebackFrame] = field(default_factory=list)
    offending_lines: list[dict[str, Any]] = field(default_factory=list)
    analysis: str = ""
    root_cause: str = ""
    fix_suggestions: list[str] = field(default_factory=list)
    corrected_code_prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "error_summary": self.error_summary,
            "severity": self.severity,
            "traceback_frames": [f.to_dict() for f in self.traceback_frames],
            "offending_lines": self.offending_lines,
            "analysis": self.analysis,
            "root_cause": self.root_cause,
            "fix_suggestions": self.fix_suggestions,
            "corrected_code_prompt": self.corrected_code_prompt,
        }


class DebugExpert:
    """Intelligent error diagnosis engine for COBOL-to-Python migrations."""

    # ------------------------------------------------------------------
    # Error classification patterns
    # ------------------------------------------------------------------

    _ERROR_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
        ("SyntaxError",        re.compile(r"SyntaxError:\s*(.+)")),
        ("IndentationError",   re.compile(r"IndentationError:\s*(.+)")),
        ("NameError",          re.compile(r"NameError:\s*(.+)")),
        ("TypeError",          re.compile(r"TypeError:\s*(.+)")),
        ("ValueError",         re.compile(r"ValueError:\s*(.+)")),
        ("IndexError",         re.compile(r"IndexError:\s*(.+)")),
        ("KeyError",           re.compile(r"KeyError:\s*(.+)")),
        ("AttributeError",     re.compile(r"AttributeError:\s*(.+)")),
        ("ZeroDivisionError",  re.compile(r"ZeroDivisionError:\s*(.+)")),
        ("ImportError",        re.compile(r"(?:Import|Module)Error:\s*(.+)")),
        ("FileNotFoundError",  re.compile(r"FileNotFoundError:\s*(.+)")),
        ("OverflowError",      re.compile(r"OverflowError:\s*(.+)")),
        ("RuntimeError",       re.compile(r"RuntimeError:\s*(.+)")),
        ("AssertionError",     re.compile(r"AssertionError:?\s*(.*)")),
    ]

    # Traceback frame pattern
    _FRAME_RE = re.compile(
        r'File "([^"]+)", line (\d+), in (\w+)\n\s+(.+)',
    )

    # ------------------------------------------------------------------
    # Severity rules   (error_type → base severity, then adjusted)
    # ------------------------------------------------------------------

    _BASE_SEVERITY: dict[str, int] = {
        "SyntaxError": 2,
        "IndentationError": 1,
        "NameError": 2,
        "TypeError": 3,
        "ValueError": 3,
        "IndexError": 3,
        "KeyError": 2,
        "AttributeError": 3,
        "ZeroDivisionError": 3,
        "ImportError": 1,
        "FileNotFoundError": 2,
        "OverflowError": 4,
        "RuntimeError": 4,
        "AssertionError": 3,
        "LogicError": 5,
    }

    # ------------------------------------------------------------------
    # COBOL-aware root-cause patterns
    # ------------------------------------------------------------------

    _COBOL_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
        # (regex on error text, root cause, category)
        (re.compile(r"name '(\w+)' is not defined"),
         "Untranslated COBOL data item or paragraph — '{0}' was referenced "
         "in COBOL but not declared in Python.",
         "missing_translation"),

        (re.compile(r"Did you mean: '(\w+)'"),
         "Likely a typo introduced during translation — Python suggests '{0}'.",
         "typo"),

        (re.compile(r"unsupported operand type.*'(\w+)'.*'(\w+)'"),
         "Type mismatch: COBOL PIC clause was mapped to '{0}' but the "
         "operation expects '{1}'. Check PIC-to-type mapping.",
         "type_mismatch"),

        (re.compile(r"can't multiply sequence"),
         "String was used where a number was expected — likely a PIC A/X "
         "field used in arithmetic. Check COBOL data types.",
         "type_mismatch"),

        (re.compile(r"global name '(\w+)' is not defined"),
         "Missing 'global' declaration — '{0}' is a module-level variable "
         "that needs a 'global' statement inside the function.",
         "scope"),

        (re.compile(r"local variable '(\w+)' referenced before assignment"),
         "Missing 'global' declaration — '{0}' needs to be declared global "
         "in the function to reference the module-level variable.",
         "scope"),

        (re.compile(r"division by zero"),
         "COBOL DIVIDE operation has no zero-guard — the divisor variable "
         "was not initialised or was zeroed out.",
         "arithmetic"),

        (re.compile(r"invalid literal for int"),
         "ACCEPT statement input not cast to the correct numeric type. "
         "Check PIC clause for the target variable.",
         "input_cast"),

        (re.compile(r"index out of range"),
         "Array/table subscript error — COBOL uses 1-based indexing, "
         "Python uses 0-based. Off-by-one likely.",
         "indexing"),
    ]

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
            Full error/traceback output.
        cobol_source : str, optional
            Original COBOL source for cross-reference.
        context : dict, optional
            RAG-retrieved context.

        Returns
        -------
        dict
            Complete diagnosis with keys: error_type, error_summary,
            severity, traceback_frames, offending_lines, analysis,
            root_cause, fix_suggestions, corrected_code_prompt.
        """
        context = context or {}
        result = DebugResult()

        # Step 1 — Classify the error
        result.error_type, result.error_summary = self._classify_error(error_message)

        # Step 2 — Parse traceback frames
        result.traceback_frames = self._parse_traceback(error_message)

        # Step 3 — Extract offending lines from the code
        result.offending_lines = self._extract_offending_lines(
            python_code, result.traceback_frames,
        )

        # Step 4 — Deep analysis
        result.analysis = self._analyse_error(
            result.error_type, result.error_summary,
            python_code, result.traceback_frames,
        )

        # Step 5 — COBOL-aware root cause
        result.root_cause = self._identify_root_cause(
            error_message, result.error_summary, cobol_source,
        )

        # Step 6 — Dynamic fix suggestions
        result.fix_suggestions = self._suggest_fixes(
            result.error_type, error_message, python_code, cobol_source,
        )

        # Step 7 — Severity
        result.severity = self._compute_severity(
            result.error_type, result.root_cause, len(result.fix_suggestions),
        )

        # Step 8 — Build the LLM prompt
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
        first_line = (
            error_message.strip().splitlines()[0]
            if error_message.strip() else "Unknown error"
        )
        return "LogicError", first_line

    # ------------------------------------------------------------------
    # Traceback parsing
    # ------------------------------------------------------------------

    def _parse_traceback(self, error_message: str) -> list[TracebackFrame]:
        """Extract structured frames from a Python traceback."""
        frames: list[TracebackFrame] = []
        for m in self._FRAME_RE.finditer(error_message):
            frames.append(TracebackFrame(
                filename=m.group(1),
                line_number=int(m.group(2)),
                function_name=m.group(3),
                code_line=m.group(4).strip(),
            ))
        return frames

    # ------------------------------------------------------------------
    # Offending line extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_offending_lines(
        code: str,
        frames: list[TracebackFrame],
    ) -> list[dict[str, Any]]:
        """Pull the actual source lines from the code that the traceback references."""
        code_lines = code.splitlines()
        offending: list[dict[str, Any]] = []

        # From traceback frames
        seen_lines: set[int] = set()
        for frame in frames:
            ln = frame.line_number
            if 1 <= ln <= len(code_lines) and ln not in seen_lines:
                seen_lines.add(ln)
                # Include surrounding context (2 lines before/after)
                start = max(0, ln - 3)
                end = min(len(code_lines), ln + 2)
                snippet = {
                    "line_number": ln,
                    "line": code_lines[ln - 1].rstrip(),
                    "context": [
                        f"{'→' if i + 1 == ln else ' '} {i + 1:4d} | {code_lines[i].rstrip()}"
                        for i in range(start, end)
                    ],
                }
                offending.append(snippet)

        return offending

    # ------------------------------------------------------------------
    # Deep analysis
    # ------------------------------------------------------------------

    @staticmethod
    def _analyse_error(
        error_type: str,
        summary: str,
        code: str,
        frames: list[TracebackFrame],
    ) -> str:
        """Build a detailed human-readable analysis."""
        code_lines = code.strip().splitlines()
        parts = [
            f"Error type  : {error_type}",
            f"Summary     : {summary}",
            f"Code size   : {len(code_lines)} lines",
            f"Stack depth : {len(frames)} frame(s)",
        ]

        if frames:
            last = frames[-1]
            parts.append(f"Origin      : {last.function_name}() at line {last.line_number}")
            parts.append(f"Statement   : {last.code_line}")

        # NameError: identify what's missing
        if error_type == "NameError":
            name_match = re.search(r"name '(\w+)'", summary)
            if name_match:
                missing = name_match.group(1)
                parts.append(f"Missing name: '{missing}'")
                # Check if it looks like a COBOL name
                if "-" not in missing and "_" in missing:
                    parts.append(
                        "  → This looks like a translated COBOL name. "
                        "Check if the original data item was extracted."
                    )
                # Check if a similar name exists
                all_names = set(re.findall(r"\b\w+\b", code))
                close = [
                    n for n in all_names
                    if n != missing and _similarity(n, missing) > 0.7
                ]
                if close:
                    parts.append(f"  → Similar names in code: {', '.join(sorted(close)[:5])}")

        # TypeError: show types involved
        if error_type == "TypeError":
            type_match = re.search(r"'(\w+)' and '(\w+)'", summary)
            if type_match:
                parts.append(
                    f"Types involved: {type_match.group(1)}, {type_match.group(2)}"
                )

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # COBOL-aware root cause identification
    # ------------------------------------------------------------------

    def _identify_root_cause(
        self,
        error_message: str,
        summary: str,
        cobol_source: str,
    ) -> str:
        """Cross-reference error with COBOL patterns to find root cause."""
        combined = f"{error_message}\n{summary}"

        for pattern, cause_template, category in self._COBOL_PATTERNS:
            m = pattern.search(combined)
            if m:
                cause = cause_template.format(*m.groups())
                # Enrich with COBOL cross-reference
                if cobol_source and category == "missing_translation":
                    name = m.group(1) if m.lastindex else ""
                    cobol_name = name.upper().replace("_", "-")
                    if cobol_name in cobol_source.upper():
                        cause += (
                            f"\n  → COBOL item '{cobol_name}' exists in source "
                            "but was not translated to Python."
                        )
                return cause

        return (
            "No specific COBOL-related root cause identified. "
            "The error may be a general Python issue."
        )

    # ------------------------------------------------------------------
    # Dynamic fix suggestions
    # ------------------------------------------------------------------

    def _suggest_fixes(
        self,
        error_type: str,
        error_message: str,
        code: str,
        cobol_source: str,
    ) -> list[str]:
        """Generate context-aware fix suggestions based on actual error content."""
        suggestions: list[str] = []

        # --- Error-type-specific suggestions ---
        if error_type == "NameError":
            name_match = re.search(r"name '(\w+)'", error_message)
            if name_match:
                missing = name_match.group(1)
                suggestions.append(
                    f"Add a declaration for '{missing}' — it may be an "
                    "untranslated COBOL data item."
                )
                # Check for 'Did you mean'
                hint = re.search(r"Did you mean: '(\w+)'", error_message)
                if hint:
                    suggestions.append(
                        f"Fix the typo: replace '{missing}' with '{hint.group(1)}'."
                    )
                # Check if global is missing
                if missing in code and f"global" not in code:
                    suggestions.append(
                        f"Add 'global {missing}' at the top of the function."
                    )

        elif error_type in ("SyntaxError", "IndentationError"):
            suggestions.append("Check for missing colons after if/for/while/def.")
            suggestions.append("Verify all parentheses and brackets are balanced.")
            if "indent" in error_message.lower():
                suggestions.append("Ensure consistent 4-space indentation (no tabs).")

        elif error_type == "TypeError":
            suggestions.append("Check PIC-to-type mapping — numeric PIC should be int or Decimal.")
            if "Decimal" in code:
                suggestions.append(
                    "Ensure Decimal values are not mixed with float literals "
                    "(use Decimal('0.30') not 0.30)."
                )
            if "NoneType" in error_message:
                suggestions.append("A function is returning None — add a return statement.")

        elif error_type == "ZeroDivisionError":
            suggestions.append("Add a zero-check guard: `if divisor != 0:` before DIVIDE.")
            if cobol_source:
                divide_match = re.search(
                    r"DIVIDE\s+(\w[\w-]*)\s+INTO", cobol_source, re.IGNORECASE,
                )
                if divide_match:
                    suggestions.append(
                        f"The COBOL DIVIDE uses '{divide_match.group(1)}' — "
                        "ensure it is initialised to a non-zero value."
                    )

        elif error_type == "ValueError":
            suggestions.append("Check ACCEPT-to-input() type conversions (int(), Decimal()).")
            suggestions.append("Validate input before numeric conversion.")

        elif error_type == "AttributeError":
            attr_match = re.search(r"'(\w+)' object has no attribute '(\w+)'", error_message)
            if attr_match:
                suggestions.append(
                    f"The type '{attr_match.group(1)}' doesn't have '{attr_match.group(2)}'. "
                    "Check the PIC-to-type mapping."
                )

        elif error_type == "IndexError":
            suggestions.append(
                "COBOL uses 1-based indexing, Python uses 0-based. "
                "Subtract 1 from all COBOL subscripts."
            )

        elif error_type == "ImportError":
            mod_match = re.search(r"No module named '(\w+)'", error_message)
            if mod_match:
                suggestions.append(f"Install missing module: pip install {mod_match.group(1)}")

        elif error_type == "LogicError":
            suggestions.append("Compare COBOL PERFORM UNTIL — the condition must be INVERTED in Python.")
            suggestions.append("Check EVALUATE/WHEN → match/case for missing branches.")
            suggestions.append("Verify paragraph execution order matches COBOL PERFORM sequence.")

        # --- Universal suggestions ---
        if not suggestions:
            suggestions.append("Review the COBOL source for constructs not yet mapped.")
            suggestions.append("Check variable scope and initialisation.")

        suggestions.append("Cross-reference with the original COBOL logic to verify correctness.")

        return suggestions

    # ------------------------------------------------------------------
    # Severity scoring
    # ------------------------------------------------------------------

    def _compute_severity(
        self,
        error_type: str,
        root_cause: str,
        num_suggestions: int,
    ) -> int:
        """Rate fix difficulty: 1 (trivial) → 5 (critical)."""
        base = self._BASE_SEVERITY.get(error_type, 3)

        # Adjust based on root cause
        if "scope" in root_cause.lower():
            base = min(base, 2)  # scope fixes are usually easy
        if "type_mismatch" in root_cause.lower() or "logic" in error_type.lower():
            base = max(base, 4)  # type/logic issues are harder

        return max(1, min(5, base))

    # ------------------------------------------------------------------
    # Prompt builder (structured, diff-oriented, with few-shot)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        code: str,
        error: str,
        cobol_source: str,
        result: DebugResult,
        context: dict[str, Any],
    ) -> str:
        """Construct a structured, chain-of-thought debugging prompt."""
        suggestions_md = "\n".join(
            f"  {i + 1}. {s}" for i, s in enumerate(result.fix_suggestions)
        )

        offending_md = ""
        if result.offending_lines:
            parts = []
            for ol in result.offending_lines:
                ctx = "\n".join(ol["context"])
                parts.append(f"**Line {ol['line_number']}:**\n```\n{ctx}\n```")
            offending_md = "\n".join(parts)

        frames_md = ""
        if result.traceback_frames:
            frames_md = "\n".join(
                f"  {i + 1}. `{f.function_name}()` at line {f.line_number}: `{f.code_line}`"
                for i, f in enumerate(result.traceback_frames)
            )

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
You are a senior Python engineer specialising in debugging COBOL-to-Python
migration code. You have deep knowledge of both COBOL semantics and Python
best practices.

## Severity
{result.severity}/5 — {"Trivial fix" if result.severity <= 2 else "Moderate complexity" if result.severity <= 3 else "Complex — requires careful analysis"}

## Error Report
- **Type**    : `{result.error_type}`
- **Message** : `{result.error_summary}`

## Call Stack ({len(result.traceback_frames)} frames)
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
{result.root_cause}

## Detailed Analysis
{result.analysis}

## Suggested Fixes
{suggestions_md}
{rag_section}

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


# ---------------------------------------------------------------------------
# Utility: string similarity (Jaccard on character bigrams)
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity on character bigrams."""
    if not a or not b:
        return 0.0
    a_lower, b_lower = a.lower(), b.lower()
    bigrams_a = {a_lower[i:i + 2] for i in range(len(a_lower) - 1)}
    bigrams_b = {b_lower[i:i + 2] for i in range(len(b_lower) - 1)}
    if not bigrams_a or not bigrams_b:
        return 0.0
    return len(bigrams_a & bigrams_b) / len(bigrams_a | bigrams_b)


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

    cobol_src = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYROLL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SALARY PIC 9(7)V99.
       01 WS-TAX    PIC 9(7)V99.
       PROCEDURE DIVISION.
           COMPUTE WS-TAX = WS-SALARY * 0.30.
"""

    expert = DebugExpert()
    result = expert.run(broken_code, error_msg, cobol_src)
    print(f"Error type  : {result['error_type']}")
    print(f"Severity    : {result['severity']}/5")
    print(f"Summary     : {result['error_summary']}")
    print(f"Root cause  : {result['root_cause']}")
    print(f"Frames      : {len(result['traceback_frames'])}")
    print(f"Offending   : {len(result['offending_lines'])} line(s)")
    print(f"Suggestions : {result['fix_suggestions']}")
    print(f"\nAnalysis:\n{result['analysis']}")
    print(f"\n--- prompt (first 500 chars) ---")
    print(result["corrected_code_prompt"][:500])
