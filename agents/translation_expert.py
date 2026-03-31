"""COBOL-to-Python translation expert with inline statement translation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agents.base import BaseExpert
from agents.prompts import TranslationPrompt


# ---------------------------------------------------------------------------
# COBOL → Python construct mapping (26 constructs)
# ---------------------------------------------------------------------------

CONSTRUCT_MAP: list[dict[str, str]] = [
    # Control flow
    {"cobol": "PERFORM … UNTIL",      "python": "while not <cond>:",         "notes": "Invert COBOL UNTIL condition"},
    {"cobol": "PERFORM … TIMES",      "python": "for _ in range(n):",        "notes": "Use range with integer count"},
    {"cobol": "PERFORM VARYING",      "python": "for i in range(s, e, st):", "notes": "Map FROM/BY/UNTIL to range()"},
    {"cobol": "PERFORM paragraph",    "python": "paragraph()",               "notes": "Map paragraph to function call"},
    {"cobol": "IF / ELSE / END-IF",   "python": "if / elif / else:",         "notes": "Direct mapping"},
    {"cobol": "EVALUATE / WHEN",      "python": "match val: case …",         "notes": "Python 3.10+ pattern matching"},
    {"cobol": "GO TO paragraph",      "python": "# WARNING: GO TO → refactor","notes": "Anti-pattern; refactor"},
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
    {"cobol": "STRING",               "python": "result = a + b + …",        "notes": "Concatenation"},
    {"cobol": "UNSTRING",             "python": "parts = s.split(delim)",    "notes": "Splitting"},
    {"cobol": "INSPECT TALLYING",     "python": "count = s.count(sub)",      "notes": "Count occurrences"},
    {"cobol": "INSPECT REPLACING",    "python": "s = s.replace(old, new)",   "notes": "Replace occurrences"},
    # I/O
    {"cobol": "DISPLAY text",         "python": "print(text)",               "notes": "String interpolation"},
    {"cobol": "ACCEPT var",           "python": "var = input(prompt)",        "notes": "Type cast if numeric"},
    {"cobol": "OPEN file",            "python": "fh = open(path, mode)",     "notes": "INPUT→'r', OUTPUT→'w'"},
    {"cobol": "READ file",            "python": "line = fh.readline()",      "notes": "Sequential read"},
    {"cobol": "WRITE record",         "python": "fh.write(record)",          "notes": "Sequential write"},
    {"cobol": "CLOSE file",           "python": "fh.close()",                "notes": "Release file handle"},
    # Special
    {"cobol": "Level-88 VALUE",       "python": "FLAG: bool = (var == val)", "notes": "Boolean condition name"},
    {"cobol": "REDEFINES",            "python": "@property / Union type",    "notes": "Alternate view of storage"},
    {"cobol": "STOP RUN",             "python": "sys.exit(0)",               "notes": "Or return from main()"},
]


# ---------------------------------------------------------------------------
# Result data structure
# ---------------------------------------------------------------------------

@dataclass
class TranslationResult:
    python_code: str = ""
    mapping_table: list[dict[str, str]] = field(default_factory=list)
    prompt_payload: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "python_code": self.python_code,
            "mapping_table": self.mapping_table,
            "prompt_payload": self.prompt_payload,
        }


# ---------------------------------------------------------------------------
# Expert
# ---------------------------------------------------------------------------

class TranslationExpert(BaseExpert):
    """Generates a Python translation from COBOL source + structural analysis."""

    def __init__(self) -> None:
        super().__init__()
        self.construct_map = CONSTRUCT_MAP

    def run(
        self,
        structure_analysis: dict[str, Any] | None = None,
        cobol_source: str = "",
        context: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        """Produce a Python skeleton with inline translations and an LLM prompt."""
        source = self.validate_source(cobol_source)
        ctx = self.validate_context(context)
        analysis = structure_analysis or {}

        result = TranslationResult()
        result.python_code = _generate_skeleton(analysis)
        result.mapping_table = self._relevant_mappings(source)
        result.prompt_payload = TranslationPrompt.build(
            source=source,
            analysis=analysis,
            python_skeleton=result.python_code,
            mapping_table=result.mapping_table,
            context=ctx,
        )

        self.logger.debug("Generated %d-char skeleton", len(result.python_code))
        return result.to_dict()

    def _relevant_mappings(self, source: str) -> list[dict[str, str]]:
        upper = source.upper()
        seen: set[str] = set()
        relevant: list[dict[str, str]] = []
        for entry in self.construct_map:
            kw = entry["cobol"].split()[0]
            if kw in upper and kw not in seen:
                relevant.append(entry)
                seen.add(kw)
        return relevant


# ---------------------------------------------------------------------------
# Skeleton generation (module-level helper, keeps expert class lean)
# ---------------------------------------------------------------------------

def _generate_skeleton(analysis: dict[str, Any]) -> str:
    lines: list[str] = [
        '"""',
        f"Auto-generated Python translation of COBOL program: "
        f"{analysis.get('program_id', 'UNKNOWN')}",
        '"""', "", "import sys", "from decimal import Decimal", "", "",
    ]

    data_items = analysis.get("data_items", [])
    all_vars: list[str] = []

    if data_items:
        lines.append("# --- Data items (WORKING-STORAGE) ---")
        for item in data_items:
            _emit_data_item(item, lines, all_vars, indent=0)
        lines += ["", ""]

    global_decl = f"    global {', '.join(all_vars)}" if all_vars else ""

    paragraph_details = analysis.get("paragraph_details", [])
    paragraphs = analysis.get("paragraphs", [])

    if paragraph_details:
        for pd in paragraph_details:
            fn = _to_py_name(pd["name"])
            lines.append(f"def {fn}():")
            lines.append(f'    """Translated from COBOL paragraph {pd["name"]}."""')
            if global_decl:
                lines.append(global_decl)
            body = _translate_body(pd.get("body", []))
            lines.extend(f"    {ln}" for ln in body) if body else lines.append("    pass")
            lines += ["", ""]
    elif paragraphs:
        for p in paragraphs:
            fn = _to_py_name(p)
            lines.append(f"def {fn}():")
            lines.append(f'    """Translated from COBOL paragraph {p}."""')
            if global_decl:
                lines.append(global_decl)
            lines += ["    pass", "", ""]

    lines.append("def main():")
    lines.append('    """Main entry point — mirrors PROCEDURE DIVISION."""')
    for p in (paragraphs or [pd["name"] for pd in paragraph_details]):
        lines.append(f"    {_to_py_name(p)}()")
    if not paragraphs and not paragraph_details:
        lines.append("    pass")
    lines += ["", "", 'if __name__ == "__main__":', "    main()", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Inline COBOL → Python statement translator
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"STOP\s+RUN", re.I),               "stop"),
    (re.compile(r"^END-IF\s*\.?\s*$", re.I),         "endif"),
    (re.compile(r"^ELSE\s*$", re.I),                 "else"),
    (re.compile(r"IF\s+(.+)", re.I),                 "if"),
    (re.compile(r"MOVE\s+(.+?)\s+TO\s+(\w[\w-]*)", re.I),   "move"),
    (re.compile(r"COMPUTE\s+(\w[\w-]*)\s*=\s*(.+)", re.I),   "compute"),
    (re.compile(r"ADD\s+(.+?)\s+TO\s+(\w[\w-]*)", re.I),     "add"),
    (re.compile(r"SUBTRACT\s+(.+?)\s+FROM\s+(\w[\w-]*)", re.I), "sub"),
    (re.compile(r"MULTIPLY\s+(.+?)\s+BY\s+(\w[\w-]*)", re.I),   "mul"),
    (re.compile(r"DIVIDE\s+(.+?)\s+INTO\s+(\w[\w-]*)", re.I),   "div"),
    (re.compile(r"DISPLAY\s+(.+)", re.I),            "display"),
    (re.compile(r"ACCEPT\s+(\w[\w-]*)", re.I),       "accept"),
    (re.compile(r"PERFORM\s+(\w[\w-]*)", re.I),      "perform"),
    (re.compile(r"INITIALIZE\s+(\w[\w-]*)", re.I),   "init"),
    (re.compile(r"GO\s+TO\s+(\w[\w-]*)", re.I),      "goto"),
]


def _to_py_name(name: str) -> str:
    return name.strip().strip(".").lower().replace("-", "_")


def _expr_to_py(expr: str) -> str:
    result = expr.strip().rstrip(".")
    return re.sub(r"\b([A-Z][\w-]*)\b", lambda m: _to_py_name(m.group(1)), result)


def _display_to_py(args: str) -> str:
    args = args.strip().rstrip(".")
    parts: list[str] = []
    cur, in_q = "", False
    for ch in args:
        if ch == "'" and not in_q:
            in_q, cur = True, cur + ch
        elif ch == "'" and in_q:
            in_q, cur = False, cur + ch
        elif ch == " " and not in_q and cur:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        parts.append(cur)

    py: list[str] = []
    for p in parts:
        p = p.strip().rstrip(".")
        if not p:
            continue
        py.append(p.replace("'", '"', 1).replace("'", '"', 1) if p.startswith("'") else _to_py_name(p))
    return f"print({', '.join(py)})" if py else "print()"


def _translate_body(body_lines: list[str]) -> list[str]:
    out: list[str] = []
    indent = 0

    def _pfx() -> str:
        return "    " * indent

    for raw in body_lines:
        line = raw.strip().rstrip(".")

        for pattern, tag in _PATTERNS:
            m = pattern.match(line)
            if not m:
                continue

            if tag == "stop":
                out.append(f"{_pfx()}sys.exit(0)")
            elif tag == "endif":
                indent = max(0, indent - 1)
            elif tag == "else":
                indent = max(0, indent - 1)
                out.append(f"{_pfx()}else:")
                indent += 1
            elif tag == "if":
                out.append(f"{_pfx()}if {_expr_to_py(m.group(1))}:")
                indent += 1
            elif tag == "move":
                src = m.group(1).strip().rstrip(".")
                tgt = _to_py_name(m.group(2))
                val = src.rstrip(".") if src.startswith("'") or src.startswith('"') else _to_py_name(src)
                out.append(f"{_pfx()}{tgt} = {val}")
            elif tag == "compute":
                out.append(f"{_pfx()}{_to_py_name(m.group(1))} = {_expr_to_py(m.group(2))}")
            elif tag == "add":
                out.append(f"{_pfx()}{_to_py_name(m.group(2))} += {_expr_to_py(m.group(1))}")
            elif tag == "sub":
                out.append(f"{_pfx()}{_to_py_name(m.group(2))} -= {_expr_to_py(m.group(1))}")
            elif tag == "mul":
                out.append(f"{_pfx()}{_to_py_name(m.group(2))} *= {_expr_to_py(m.group(1))}")
            elif tag == "div":
                out.append(f"{_pfx()}{_to_py_name(m.group(2))} //= {_expr_to_py(m.group(1))}")
            elif tag == "display":
                out.append(f"{_pfx()}{_display_to_py(m.group(1))}")
            elif tag == "accept":
                v = _to_py_name(m.group(1))
                out.append(f'{_pfx()}{v} = input("{v}: ")')
            elif tag == "perform":
                out.append(f"{_pfx()}{_to_py_name(m.group(1))}()")
            elif tag == "init":
                out.append(f"{_pfx()}{_to_py_name(m.group(1))} = 0  # INITIALIZE")
            elif tag == "goto":
                t = _to_py_name(m.group(1))
                out += [f"{_pfx()}# WARNING: GO TO {t}", f"{_pfx()}{t}()", f"{_pfx()}return"]
            break
        else:
            out.append(f"{_pfx()}# COBOL: {raw.strip()}")

    return out


# ---------------------------------------------------------------------------
# Data-item helpers
# ---------------------------------------------------------------------------

def _emit_data_item(
    item: dict[str, Any], lines: list[str],
    all_vars: list[str], indent: int,
) -> None:
    prefix = "    " * indent
    name, pic = item["name"], item.get("picture", "")
    py_name = _to_py_name(name)
    children = item.get("children", [])

    if item.get("is_level_88"):
        parent = all_vars[-1] if all_vars else "None"
        lines.append(f'{prefix}# Level-88: {py_name} is True when {parent} == "{item.get("value", "")}"')
        return

    if children and not pic:
        lines.append(f"{prefix}# Group: {name}")
        for child in children:
            _emit_data_item(child, lines, all_vars, indent)
        return

    py_type = _pic_to_type(pic)
    default = _pic_to_default(pic, item.get("value", ""))
    redef = item.get("redefines", "")

    if redef:
        lines.append(f"{prefix}{py_name}: {py_type} = {_to_py_name(redef)}  # REDEFINES")
    else:
        lines.append(f"{prefix}{py_name}: {py_type} = {default}")
    all_vars.append(py_name)


def _pic_to_type(pic: str) -> str:
    if not pic:
        return "str"
    upper = pic.upper()
    if "V" in upper or ("9" in upper and "." in upper):
        return "Decimal"
    if upper.startswith(("9", "S9")):
        return "int"
    return "str"


def _pic_to_default(pic: str, value: str) -> str:
    if value:
        try:
            return f'Decimal("{value}")' if "." in value else str(int(value)) if value.lstrip("-").isdigit() else f'"{value}"'
        except ValueError:
            return f'"{value}"'
    t = _pic_to_type(pic)
    return {"int": "0", "Decimal": 'Decimal("0")'}.get(t, '""')
