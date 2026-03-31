"""
translation_expert.py — COBOL-to-Python translation expert.

Uses a construct mapping table to translate COBOL patterns into their
Python equivalents.  The expert now performs TWO levels of translation:

  1. **Skeleton generation** — module structure, data items, function
     signatures, and `global` declarations.
  2. **Inline body translation** — parses each paragraph's COBOL
     statements (MOVE, DISPLAY, COMPUTE, ADD, PERFORM, IF, …) and
     emits real Python lines instead of empty ``pass`` stubs.

A structured LLM prompt with chain-of-thought instructions and a
few-shot example is also produced so an LLM can refine the output.

Expanded mapping table (26 constructs):
  PERFORM … UNTIL   → while loop
  PERFORM … TIMES   → for loop with range()
  PERFORM VARYING    → for loop with range(start, stop, step)
  PERFORM paragraph  → function call
  MOVE a TO b        → b = a
  IF / ELSE          → if / else
  EVALUATE / WHEN    → match / case (Python 3.10+)
  DISPLAY            → print()
  ACCEPT             → input()
  COMPUTE            → arithmetic expression
  ADD / SUBTRACT     → augmented assignment (+=, -=)
  MULTIPLY / DIVIDE  → augmented assignment (*, /)
  STRING / UNSTRING  → str concat / split
  INSPECT TALLYING   → str.count()
  INSPECT REPLACING  → str.replace()
  READ / WRITE       → file I/O
  OPEN / CLOSE       → open() / .close()
  GO TO              → flagged anti-pattern
  INITIALIZE         → reset to default
  SET                → boolean/index assignment
  EXIT PARAGRAPH     → return
  CONTINUE           → pass
  Level-88           → bool constant
  REDEFINES          → @property / union type
  STOP RUN           → sys.exit() or return
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# COBOL → Python construct mapping reference (expanded)
# ---------------------------------------------------------------------------
CONSTRUCT_MAP: list[dict[str, str]] = [
    # Control flow
    {"cobol": "PERFORM … UNTIL",      "python": "while not <cond>:",         "notes": "Invert COBOL UNTIL condition"},
    {"cobol": "PERFORM … TIMES",      "python": "for _ in range(n):",        "notes": "Use range with integer count"},
    {"cobol": "PERFORM VARYING",      "python": "for i in range(s, e, st):", "notes": "Map FROM/BY/UNTIL to range()"},
    {"cobol": "PERFORM paragraph",    "python": "paragraph()",               "notes": "Map paragraph to function call"},
    {"cobol": "IF / ELSE / END-IF",   "python": "if / elif / else:",         "notes": "Direct mapping"},
    {"cobol": "EVALUATE / WHEN",      "python": "match val: case …",         "notes": "Python 3.10+ pattern matching"},
    {"cobol": "GO TO paragraph",      "python": "# WARNING: GO TO → refactor","notes": "Anti-pattern; refactor to function call"},
    {"cobol": "EXIT PARAGRAPH",       "python": "return",                    "notes": "Early exit from function"},
    {"cobol": "CONTINUE",             "python": "pass",                      "notes": "No-op"},

    # Data movement & arithmetic
    {"cobol": "MOVE a TO b",          "python": "b = a",                     "notes": "Simple assignment"},
    {"cobol": "COMPUTE expr",         "python": "var = <expr>",              "notes": "Translate arithmetic operators"},
    {"cobol": "ADD a TO b",           "python": "b += a",                    "notes": "Augmented assignment"},
    {"cobol": "SUBTRACT a FROM b",    "python": "b -= a",                    "notes": "Augmented assignment"},
    {"cobol": "MULTIPLY a BY b",      "python": "b *= a",                    "notes": "Augmented assignment"},
    {"cobol": "DIVIDE a INTO b",      "python": "b //= a  or  b /= a",      "notes": "Choose int / float per PIC"},
    {"cobol": "INITIALIZE var",       "python": "var = default",             "notes": "Reset to PIC-based default"},
    {"cobol": "SET flag TO TRUE",     "python": "flag = True",               "notes": "Boolean / index assignment"},

    # String handling
    {"cobol": "STRING",               "python": "result = a + b + …",        "notes": "String concatenation"},
    {"cobol": "UNSTRING",             "python": "parts = s.split(delim)",    "notes": "String splitting"},
    {"cobol": "INSPECT TALLYING",     "python": "count = s.count(sub)",      "notes": "Count occurrences"},
    {"cobol": "INSPECT REPLACING",    "python": "s = s.replace(old, new)",   "notes": "Replace occurrences"},

    # I/O
    {"cobol": "DISPLAY text",         "python": "print(text)",               "notes": "String interpolation for vars"},
    {"cobol": "ACCEPT var",           "python": "var = input(prompt)",        "notes": "Add type cast if PIC is numeric"},
    {"cobol": "OPEN file",            "python": "fh = open(path, mode)",     "notes": "Map INPUT→'r', OUTPUT→'w'"},
    {"cobol": "READ file",            "python": "line = fh.readline()",      "notes": "Sequential read"},
    {"cobol": "WRITE record",         "python": "fh.write(record)",          "notes": "Sequential write"},
    {"cobol": "CLOSE file",           "python": "fh.close()",                "notes": "Release file handle"},

    # Level-88 / REDEFINES
    {"cobol": "Level-88 VALUE",       "python": "FLAG: bool = (var == val)", "notes": "Boolean condition name"},
    {"cobol": "REDEFINES",            "python": "@property / Union type",    "notes": "Alternate view of same storage"},

    # Termination
    {"cobol": "STOP RUN",             "python": "sys.exit(0)",               "notes": "Or return from main()"},
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
            Keys: python_code (skeleton with inline translations),
            mapping_table, prompt_payload.
        """
        context = context or {}
        result = TranslationResult()

        # Build a skeleton with inline body translations
        result.python_code = self._generate_skeleton(structure_analysis)

        # Attach the relevant subset of the mapping table
        result.mapping_table = self._relevant_mappings(cobol_source)

        # Build the full LLM prompt with CoT + few-shot
        result.prompt_payload = self._build_prompt(
            cobol_source, structure_analysis, result, context,
        )

        return result.to_dict()

    # ------------------------------------------------------------------
    # Skeleton generator (with inline translation)
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_skeleton(analysis: dict[str, Any]) -> str:
        """Create a Python code skeleton with translated paragraph bodies."""
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

        # Collect all data-item names for `global` declarations
        data_items = analysis.get("data_items", [])
        all_var_names: list[str] = []

        # --- Data items → module-level variables ---
        if data_items:
            lines.append("# --- Data items (WORKING-STORAGE) ---")
            for item in data_items:
                _emit_data_item(item, lines, all_var_names, indent=0)
            lines.append("")
            lines.append("")

        # Build a global declaration line for use inside functions
        global_decl = ""
        if all_var_names:
            global_decl = f"    global {', '.join(all_var_names)}"

        # --- Paragraphs → functions with inline-translated bodies ---
        paragraph_details = analysis.get("paragraph_details", [])
        paragraphs = analysis.get("paragraphs", [])

        if paragraph_details:
            for pd in paragraph_details:
                fn_name = pd["name"].lower().replace("-", "_")
                lines.append(f"def {fn_name}():")
                lines.append(f'    """Translated from COBOL paragraph {pd["name"]}."""')
                if global_decl:
                    lines.append(global_decl)
                body = _translate_paragraph_body(pd.get("body", []))
                if body:
                    lines.extend(f"    {ln}" for ln in body)
                else:
                    lines.append("    pass")
                lines.append("")
                lines.append("")
        elif paragraphs:
            # Fallback: paragraph names only (no body data)
            for para in paragraphs:
                fn_name = para.lower().replace("-", "_")
                lines.append(f"def {fn_name}():")
                lines.append(f'    """Translated from COBOL paragraph {para}."""')
                if global_decl:
                    lines.append(global_decl)
                lines.append("    pass")
                lines.append("")
                lines.append("")

        # --- Main entry point ---
        lines.append("def main():")
        lines.append('    """Main entry point — mirrors PROCEDURE DIVISION."""')
        targets = paragraphs or [pd["name"] for pd in paragraph_details]
        if targets:
            for para in targets:
                fn_name = para.lower().replace("-", "_")
                lines.append(f"    {fn_name}()")
        else:
            lines.append("    pass")
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
        seen_keywords: set[str] = set()
        for entry in self.construct_map:
            keyword = entry["cobol"].split()[0]
            if keyword in upper and keyword not in seen_keywords:
                relevant.append(entry)
                seen_keywords.add(keyword)
        return relevant

    # ------------------------------------------------------------------
    # Prompt builder (with chain-of-thought + few-shot example)
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

## Python Skeleton (auto-generated, may need refinement)
```python
{result.python_code}
```
{rag_section}

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


# ---------------------------------------------------------------------------
# Inline COBOL → Python statement translator
# ---------------------------------------------------------------------------

# Regex patterns for common COBOL statements
_MOVE_RE = re.compile(
    r"MOVE\s+(.+?)\s+TO\s+(\w[\w-]*)", re.IGNORECASE
)
_DISPLAY_RE = re.compile(
    r"DISPLAY\s+(.+)", re.IGNORECASE
)
_COMPUTE_RE = re.compile(
    r"COMPUTE\s+(\w[\w-]*)\s*=\s*(.+)", re.IGNORECASE
)
_ADD_RE = re.compile(
    r"ADD\s+(.+?)\s+TO\s+(\w[\w-]*)", re.IGNORECASE
)
_SUBTRACT_RE = re.compile(
    r"SUBTRACT\s+(.+?)\s+FROM\s+(\w[\w-]*)", re.IGNORECASE
)
_MULTIPLY_RE = re.compile(
    r"MULTIPLY\s+(.+?)\s+BY\s+(\w[\w-]*)", re.IGNORECASE
)
_DIVIDE_RE = re.compile(
    r"DIVIDE\s+(.+?)\s+INTO\s+(\w[\w-]*)", re.IGNORECASE
)
_PERFORM_RE = re.compile(
    r"PERFORM\s+(\w[\w-]*)", re.IGNORECASE
)
_ACCEPT_RE = re.compile(
    r"ACCEPT\s+(\w[\w-]*)", re.IGNORECASE
)
_STOP_RE = re.compile(
    r"STOP\s+RUN", re.IGNORECASE
)
_IF_RE = re.compile(
    r"IF\s+(.+)", re.IGNORECASE
)
_ELSE_RE = re.compile(
    r"^ELSE\s*$", re.IGNORECASE
)
_END_IF_RE = re.compile(
    r"^END-IF\s*\.?\s*$", re.IGNORECASE
)
_INITIALIZE_RE = re.compile(
    r"INITIALIZE\s+(\w[\w-]*)", re.IGNORECASE
)
_GO_TO_RE = re.compile(
    r"GO\s+TO\s+(\w[\w-]*)", re.IGNORECASE
)


def _cobol_name_to_py(name: str) -> str:
    """Convert a COBOL identifier to a Python-style snake_case name."""
    return name.strip().strip(".").lower().replace("-", "_")


def _cobol_expr_to_py(expr: str) -> str:
    """Convert a COBOL arithmetic/string expression to Python syntax."""
    result = expr.strip().rstrip(".")
    # Replace COBOL names with snake_case
    result = re.sub(r"\b([A-Z][\w-]*)\b", lambda m: _cobol_name_to_py(m.group(1)), result)
    # COBOL uses ** for exponentiation (same as Python)
    return result


def _cobol_display_to_py(args: str) -> str:
    """Convert DISPLAY arguments to a Python print() call."""
    args = args.strip().rstrip(".")
    # Split on spaces, but keep quoted strings intact
    parts: list[str] = []
    current = ""
    in_quote = False
    for ch in args:
        if ch == "'" and not in_quote:
            in_quote = True
            current += ch
        elif ch == "'" and in_quote:
            in_quote = False
            current += ch
        elif ch == " " and not in_quote and current:
            parts.append(current)
            current = ""
        else:
            current += ch
    if current:
        parts.append(current)

    py_parts: list[str] = []
    for p in parts:
        p = p.strip().rstrip(".")
        if not p:
            continue
        if p.startswith("'") and p.endswith("'"):
            py_parts.append(p.replace("'", '"', 1).replace("'", '"', 1))
        else:
            py_parts.append(_cobol_name_to_py(p))

    if len(py_parts) == 1:
        return f"print({py_parts[0]})"
    return f"print({', '.join(py_parts)})"


def _translate_paragraph_body(body_lines: list[str]) -> list[str]:
    """Translate a list of raw COBOL statement lines to Python lines.

    This produces best-effort Python — not perfect for deeply nested
    or complex constructs, but much better than empty stubs.
    """
    py_lines: list[str] = []
    indent_level = 0

    def _indent() -> str:
        return "    " * indent_level

    for raw_line in body_lines:
        line = raw_line.strip().rstrip(".")

        # STOP RUN
        if _STOP_RE.match(line):
            py_lines.append(f"{_indent()}sys.exit(0)")
            continue

        # END-IF
        if _END_IF_RE.match(line):
            if indent_level > 0:
                indent_level -= 1
            continue

        # ELSE
        if _ELSE_RE.match(line):
            if indent_level > 0:
                indent_level -= 1
            py_lines.append(f"{_indent()}else:")
            indent_level += 1
            continue

        # IF
        m = _IF_RE.match(line)
        if m:
            cond = _cobol_expr_to_py(m.group(1))
            py_lines.append(f"{_indent()}if {cond}:")
            indent_level += 1
            continue

        # MOVE
        m = _MOVE_RE.match(line)
        if m:
            src = m.group(1).strip().rstrip(".")
            tgt = _cobol_name_to_py(m.group(2))
            if src.startswith("'") or src.startswith('"'):
                py_lines.append(f'{_indent()}{tgt} = {src.rstrip(".")}')
            else:
                py_lines.append(f"{_indent()}{tgt} = {_cobol_name_to_py(src)}")
            continue

        # COMPUTE
        m = _COMPUTE_RE.match(line)
        if m:
            tgt = _cobol_name_to_py(m.group(1))
            expr = _cobol_expr_to_py(m.group(2))
            py_lines.append(f"{_indent()}{tgt} = {expr}")
            continue

        # ADD
        m = _ADD_RE.match(line)
        if m:
            val = _cobol_expr_to_py(m.group(1))
            tgt = _cobol_name_to_py(m.group(2))
            py_lines.append(f"{_indent()}{tgt} += {val}")
            continue

        # SUBTRACT
        m = _SUBTRACT_RE.match(line)
        if m:
            val = _cobol_expr_to_py(m.group(1))
            tgt = _cobol_name_to_py(m.group(2))
            py_lines.append(f"{_indent()}{tgt} -= {val}")
            continue

        # MULTIPLY
        m = _MULTIPLY_RE.match(line)
        if m:
            val = _cobol_expr_to_py(m.group(1))
            tgt = _cobol_name_to_py(m.group(2))
            py_lines.append(f"{_indent()}{tgt} *= {val}")
            continue

        # DIVIDE
        m = _DIVIDE_RE.match(line)
        if m:
            val = _cobol_expr_to_py(m.group(1))
            tgt = _cobol_name_to_py(m.group(2))
            py_lines.append(f"{_indent()}{tgt} //= {val}")
            continue

        # DISPLAY
        m = _DISPLAY_RE.match(line)
        if m:
            py_lines.append(f"{_indent()}{_cobol_display_to_py(m.group(1))}")
            continue

        # ACCEPT
        m = _ACCEPT_RE.match(line)
        if m:
            var = _cobol_name_to_py(m.group(1))
            py_lines.append(f'{_indent()}{var} = input("{var}: ")')
            continue

        # PERFORM (call another paragraph)
        m = _PERFORM_RE.match(line)
        if m:
            fn = _cobol_name_to_py(m.group(1))
            py_lines.append(f"{_indent()}{fn}()")
            continue

        # INITIALIZE
        m = _INITIALIZE_RE.match(line)
        if m:
            var = _cobol_name_to_py(m.group(1))
            py_lines.append(f"{_indent()}{var} = 0  # INITIALIZE — reset to default")
            continue

        # GO TO (flagged)
        m = _GO_TO_RE.match(line)
        if m:
            target = _cobol_name_to_py(m.group(1))
            py_lines.append(f"{_indent()}# WARNING: GO TO {target}() — refactor to function call")
            py_lines.append(f"{_indent()}{target}()")
            py_lines.append(f"{_indent()}return")
            continue

        # Anything else — emit as comment
        py_lines.append(f"{_indent()}# COBOL: {raw_line.strip()}")

    return py_lines


# ---------------------------------------------------------------------------
# Data-item emission helpers
# ---------------------------------------------------------------------------

def _emit_data_item(
    item: dict[str, Any],
    lines: list[str],
    all_var_names: list[str],
    indent: int,
) -> None:
    """Emit a data item (and its children) as Python declarations."""
    prefix = "    " * indent
    name = item["name"]
    py_name = _cobol_name_to_py(name)
    pic = item.get("picture", "")
    value = item.get("value", "")
    children = item.get("children", [])
    is_88 = item.get("is_level_88", False)
    redefines = item.get("redefines", "")

    if is_88:
        # Level-88 → bool constant
        parent_var = all_var_names[-1] if all_var_names else "None"
        lines.append(
            f'{prefix}# Level-88: {py_name} is True when '
            f'{parent_var} == "{value}"'
        )
        return

    if children and not pic:
        # Group item → dataclass-style dict or comment block
        lines.append(f"{prefix}# Group: {name}")
        for child in children:
            _emit_data_item(child, lines, all_var_names, indent)
        return

    py_type = _pic_to_python_type(pic)
    default = _pic_to_default(pic, value)

    if redefines:
        ref = _cobol_name_to_py(redefines)
        lines.append(f"{prefix}{py_name}: {py_type} = {ref}  # REDEFINES {redefines}")
    else:
        lines.append(f"{prefix}{py_name}: {py_type} = {default}")

    all_var_names.append(py_name)


# ---------------------------------------------------------------------------
# PIC clause → Python type helpers (bug fix: operator precedence)
# ---------------------------------------------------------------------------

def _pic_to_python_type(pic: str) -> str:
    """Map a COBOL PIC clause to a Python type annotation."""
    if not pic:
        return "str"
    upper = pic.upper()
    # Fixed: parentheses around the OR to avoid precedence bug
    if "V" in upper or ("9" in upper and "." in upper):
        return "Decimal"
    if upper.startswith("9") or upper.startswith("S9"):
        return "int"
    if upper.startswith("A") or upper.startswith("X"):
        return "str"
    return "str"


def _pic_to_default(pic: str, value: str) -> str:
    """Derive a Python default value from PIC and VALUE clauses."""
    if value:
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

    print("=== Python Code (with inline translations) ===")
    print(result["python_code"])
    print("\n=== Relevant Mappings ===")
    for m in result["mapping_table"]:
        print(f"  {m['cobol']:25s} → {m['python']}")
    print("\n=== Prompt (first 500 chars) ===")
    print(result["prompt_payload"][:500])
