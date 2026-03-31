"""
translation_expert.py — COBOL-to-Python translation expert.

Uses a construct mapping table to translate COBOL patterns into their
Python equivalents, then assembles a structured prompt that an LLM can
use to generate the final Python code.

Mapping table (selected highlights):
  PERFORM … UNTIL  → while loop
  PERFORM … TIMES  → for loop with range()
  PERFORM para     → function call
  MOVE a TO b      → b = a
  IF / ELSE        → if / else
  EVALUATE / WHEN  → match / case (Python 3.10+)
  DISPLAY          → print()
  ACCEPT           → input()
  COMPUTE          → arithmetic expression
  ADD / SUBTRACT   → augmented assignment (+=, -=)
  STRING / UNSTRING→ str concat / split
  STOP RUN         → sys.exit() or return
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# COBOL → Python construct mapping reference
# ---------------------------------------------------------------------------
CONSTRUCT_MAP: list[dict[str, str]] = [
    {"cobol": "PERFORM … UNTIL",  "python": "while not <cond>:",     "notes": "Invert COBOL UNTIL condition"},
    {"cobol": "PERFORM … TIMES",  "python": "for _ in range(n):",    "notes": "Use range with integer count"},
    {"cobol": "PERFORM paragraph","python": "paragraph()",            "notes": "Map paragraph to function call"},
    {"cobol": "MOVE a TO b",      "python": "b = a",                  "notes": "Simple assignment"},
    {"cobol": "IF / ELSE / END-IF","python": "if / elif / else:",     "notes": "Direct mapping"},
    {"cobol": "EVALUATE / WHEN",  "python": "match val: case …",      "notes": "Python 3.10+ structural pattern matching"},
    {"cobol": "DISPLAY text",     "python": "print(text)",            "notes": "String interpolation for variables"},
    {"cobol": "ACCEPT var",       "python": "var = input(prompt)",    "notes": "Add type cast if PIC is numeric"},
    {"cobol": "COMPUTE expr",     "python": "var = <expr>",           "notes": "Translate arithmetic operators"},
    {"cobol": "ADD a TO b",       "python": "b += a",                 "notes": "Augmented assignment"},
    {"cobol": "SUBTRACT a FROM b","python": "b -= a",                 "notes": "Augmented assignment"},
    {"cobol": "MULTIPLY a BY b",  "python": "b *= a",                 "notes": "Augmented assignment"},
    {"cobol": "DIVIDE a INTO b",  "python": "b //= a  or  b /= a",   "notes": "Choose int / float per PIC clause"},
    {"cobol": "STRING",           "python": "result = a + b + …",     "notes": "String concatenation"},
    {"cobol": "UNSTRING",         "python": "parts = s.split(delim)", "notes": "String splitting"},
    {"cobol": "STOP RUN",         "python": "sys.exit(0)",            "notes": "Or return from main()"},
]


@dataclass
class TranslationResult:
    """Structured output from the TranslationExpert."""

    python_code: str = ""
    mapping_table: list[dict[str, str]] = field(default_factory=list)
    prompt_payload: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "python_code": self.python_code,
            "mapping_table": self.mapping_table,
            "prompt_payload": self.prompt_payload,
        }


class TranslationExpert:
    """Generates a Python translation from COBOL source + structural analysis."""

    def __init__(self) -> None:
        self.construct_map = CONSTRUCT_MAP

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        structure_analysis: dict[str, Any],
        cobol_source: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Produce a translation prompt and skeleton Python code.

        Parameters
        ----------
        structure_analysis : dict
            Output of ``StructureExpert.run()``.
        cobol_source : str
            Original COBOL source code.
        context : dict, optional
            RAG-retrieved context (coding patterns, domain hints).

        Returns
        -------
        dict
            Keys: python_code (skeleton), mapping_table, prompt_payload.
        """
        context = context or {}
        result = TranslationResult()

        # Build a skeleton from the structural analysis
        result.python_code = self._generate_skeleton(structure_analysis)

        # Attach the relevant subset of the mapping table
        result.mapping_table = self._relevant_mappings(cobol_source)

        # Build the full LLM prompt
        result.prompt_payload = self._build_prompt(
            cobol_source, structure_analysis, result, context,
        )

        return result.to_dict()

    # ------------------------------------------------------------------
    # Skeleton generator
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_skeleton(analysis: dict[str, Any]) -> str:
        """Create a Python code skeleton from structure analysis."""
        lines: list[str] = [
            '"""',
            f"Auto-generated Python translation of COBOL program: "
            f"{analysis.get('program_id', 'UNKNOWN')}",
            '"""',
            "",
            "import sys",
            "from decimal import Decimal",
            "",
            "",
        ]

        # Data items → module-level variables
        data_items = analysis.get("data_items", [])
        if data_items:
            lines.append("# --- Data items (WORKING-STORAGE) ---")
            for item in data_items:
                py_name = item["name"].lower().replace("-", "_")
                py_type = _pic_to_python_type(item.get("picture", ""))
                default = _pic_to_default(item.get("picture", ""), item.get("value", ""))
                lines.append(f"{py_name}: {py_type} = {default}")
            lines.append("")
            lines.append("")

        # Paragraphs → functions
        paragraphs = analysis.get("paragraphs", [])
        if paragraphs:
            for para in paragraphs:
                fn_name = para.lower().replace("-", "_")
                lines.append(f"def {fn_name}():")
                lines.append(f'    """Translated from COBOL paragraph {para}."""')
                lines.append("    pass  # LLM will fill implementation")
                lines.append("")
                lines.append("")

        # Main entry point
        lines.append("def main():")
        lines.append('    """Main entry point — mirrors PROCEDURE DIVISION."""')
        if paragraphs:
            for para in paragraphs:
                fn_name = para.lower().replace("-", "_")
                lines.append(f"    {fn_name}()")
        else:
            lines.append("    pass  # LLM will fill implementation")
        lines.append("")
        lines.append("")
        lines.append('if __name__ == "__main__":')
        lines.append("    main()")
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    def _relevant_mappings(self, source: str) -> list[dict[str, str]]:
        """Return only the mapping entries whose COBOL keyword appears in source."""
        upper = source.upper()
        relevant: list[dict[str, str]] = []
        for entry in self.construct_map:
            keyword = entry["cobol"].split()[0]
            if keyword in upper:
                relevant.append(entry)
        return relevant

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        source: str,
        analysis: dict[str, Any],
        result: TranslationResult,
        context: dict[str, Any],
    ) -> str:
        """Assemble the structured translation prompt for the LLM."""
        mapping_md = "\n".join(
            f"| {m['cobol']} | {m['python']} | {m['notes']} |"
            for m in result.mapping_table
        )
        rag_section = ""
        if context:
            rag_section = (
                "\n## Retrieved Context (RAG)\n"
                + "\n".join(f"- {k}: {v}" for k, v in context.items())
            )

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

## Python Skeleton
```python
{result.python_code}
```
{rag_section}

## Instructions
1. Replace every `pass` placeholder with the correct Python logic.
2. Preserve the function-per-paragraph structure.
3. Use `Decimal` for numeric fields with implied decimals (PIC 9(n)V99).
4. Handle COBOL-specific idioms:
   - Level-88 items → boolean constants / enums.
   - REDEFINES → union types or named tuples.
   - COPY books → import statements.
5. Add type hints and docstrings.
6. Return the complete Python file content only, no explanations.
"""


# ---------------------------------------------------------------------------
# PIC clause → Python type helpers
# ---------------------------------------------------------------------------

def _pic_to_python_type(pic: str) -> str:
    """Map a COBOL PIC clause to a Python type annotation."""
    if not pic:
        return "str"
    upper = pic.upper()
    if "V" in upper or "9" in upper and "." in upper:
        return "Decimal"
    if upper.startswith("9") or upper.startswith("S9"):
        return "int"
    if upper.startswith("A") or upper.startswith("X"):
        return "str"
    return "str"


def _pic_to_default(pic: str, value: str) -> str:
    """Derive a Python default value from PIC and VALUE clauses."""
    if value:
        # Numeric value
        try:
            if "." in value:
                return f'Decimal("{value}")'
            int(value)
            return value
        except ValueError:
            return f'"{value}"'
    py_type = _pic_to_python_type(pic)
    if py_type == "int":
        return "0"
    if py_type == "Decimal":
        return 'Decimal("0")'
    return '""'


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from agents.structure_expert import StructureExpert

    sample = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYROLL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SALARY PIC 9(7)V99.
       01 WS-TAX    PIC 9(7)V99.
       PROCEDURE DIVISION.
       MAIN-LOGIC.
           PERFORM CALCULATE-TAX.
           PERFORM PRINT-RESULT.
           STOP RUN.
       CALCULATE-TAX.
           COMPUTE WS-TAX = WS-SALARY * 0.30.
       PRINT-RESULT.
           DISPLAY 'Tax: ' WS-TAX.
    """

    struct = StructureExpert().run(sample)
    expert = TranslationExpert()
    result = expert.run(struct, sample)

    print("=== Python Skeleton ===")
    print(result["python_code"])
    print("\n=== Relevant Mappings ===")
    for m in result["mapping_table"]:
        print(f"  {m['cobol']:25s} → {m['python']}")
    print("\n=== Prompt (first 400 chars) ===")
    print(result["prompt_payload"][:400])
