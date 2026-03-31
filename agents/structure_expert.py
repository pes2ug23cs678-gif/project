"""
structure_expert.py — COBOL structure analysis expert.

Parses raw COBOL source into a structural map:
  • Divisions (IDENTIFICATION, ENVIRONMENT, DATA, PROCEDURE)
  • Sections within each division
  • Paragraphs within PROCEDURE DIVISION (names AND bodies)
  • Data items from DATA DIVISION (level numbers + PIC clauses)
  • Level-88 boolean items
  • REDEFINES relationships
  • A human-readable flow summary

The parsed structure is used downstream by the TranslationExpert and
TestExpert.  Additionally, a prompt_payload is generated so an LLM can
refine or enrich the structural analysis if needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DataItem:
    """A single COBOL data item extracted from the DATA DIVISION."""

    level: str
    name: str
    picture: str = ""
    value: str = ""
    is_level_88: bool = False
    redefines: str = ""
    children: list[DataItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "level": self.level,
            "name": self.name,
            "picture": self.picture,
            "value": self.value,
        }
        if self.is_level_88:
            d["is_level_88"] = True
        if self.redefines:
            d["redefines"] = self.redefines
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


@dataclass
class ParagraphDetail:
    """A paragraph name together with its raw COBOL body lines."""

    name: str
    body_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "body": self.body_lines}


@dataclass
class StructureAnalysis:
    """Complete structural breakdown of a COBOL program."""

    program_id: str = ""
    divisions: list[str] = field(default_factory=list)
    sections: dict[str, list[str]] = field(default_factory=dict)
    paragraphs: list[str] = field(default_factory=list)
    paragraph_details: list[ParagraphDetail] = field(default_factory=list)
    data_items: list[DataItem] = field(default_factory=list)
    flow_summary: str = ""
    prompt_payload: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "divisions": self.divisions,
            "sections": {k: v for k, v in self.sections.items()},
            "paragraphs": self.paragraphs,
            "paragraph_details": [p.to_dict() for p in self.paragraph_details],
            "data_items": [d.to_dict() for d in self.data_items],
            "flow_summary": self.flow_summary,
            "prompt_payload": self.prompt_payload,
        }


class StructureExpert:
    """Parses COBOL source code and produces a structured analysis."""

    # Regex patterns for COBOL constructs
    _DIVISION_RE = re.compile(
        r"^\s*(\w[\w-]*)\s+DIVISION\s*\.", re.MULTILINE | re.IGNORECASE
    )
    _SECTION_RE = re.compile(
        r"^\s*(\w[\w-]*)\s+SECTION\s*\.", re.MULTILINE | re.IGNORECASE
    )
    _PROGRAM_ID_RE = re.compile(
        r"PROGRAM-ID\.\s*(\w[\w-]*)", re.IGNORECASE
    )
    _PARAGRAPH_RE = re.compile(
        r"^       (\w[\w-]*)\.\s*$", re.MULTILINE
    )
    _DATA_ITEM_RE = re.compile(
        r"^\s*(\d{2})\s+(\w[\w-]*)"
        r"(?:\s+REDEFINES\s+(\w[\w-]*))?"
        r"(?:\s+PIC(?:TURE)?\s+([\w\(\)\.VS]+))?"
        r"(?:\s+VALUE\s+(.+?))?\s*\.",
        re.MULTILINE | re.IGNORECASE,
    )
    _LEVEL_88_RE = re.compile(
        r"^\s*88\s+(\w[\w-]*)\s+VALUE(?:S)?\s+(.+?)\s*\.",
        re.MULTILINE | re.IGNORECASE,
    )

    # COBOL verbs that should NOT be treated as paragraph names
    _KEYWORDS = frozenset({
        "STOP", "DISPLAY", "MOVE", "PERFORM", "IF", "ELSE",
        "END-IF", "EVALUATE", "END-EVALUATE", "ACCEPT", "ADD",
        "SUBTRACT", "MULTIPLY", "DIVIDE", "COMPUTE", "GO",
        "OPEN", "READ", "WRITE", "CLOSE", "CALL", "STRING",
        "UNSTRING", "INSPECT", "INITIALIZE", "SET", "EXIT",
        "CONTINUE", "SEARCH", "SORT", "MERGE", "RETURN",
        "RELEASE", "START", "DELETE", "REWRITE",
    })

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        cobol_source: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyse *cobol_source* and return a structural map.

        Parameters
        ----------
        cobol_source : str
            Raw COBOL source code.
        context : dict, optional
            RAG-retrieved context (reserved for future enrichment).

        Returns
        -------
        dict
            Keys: program_id, divisions, sections, paragraphs,
            paragraph_details, data_items, flow_summary, prompt_payload.
        """
        context = context or {}
        analysis = StructureAnalysis()

        analysis.program_id = self._extract_program_id(cobol_source)
        analysis.divisions = self._extract_divisions(cobol_source)
        analysis.sections = self._extract_sections(cobol_source)
        para_details = self._extract_paragraphs_with_bodies(cobol_source)
        analysis.paragraphs = [p.name for p in para_details]
        analysis.paragraph_details = para_details
        analysis.data_items = self._extract_data_items(cobol_source)
        analysis.flow_summary = self._build_flow_summary(analysis)
        analysis.prompt_payload = self._build_prompt(
            cobol_source, analysis, context,
        )

        return analysis.to_dict()

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _extract_program_id(self, source: str) -> str:
        match = self._PROGRAM_ID_RE.search(source)
        return match.group(1) if match else "UNKNOWN"

    def _extract_divisions(self, source: str) -> list[str]:
        return [m.group(1).upper() for m in self._DIVISION_RE.finditer(source)]

    def _extract_sections(self, source: str) -> dict[str, list[str]]:
        """Map each division to its child sections."""
        divisions_pos: list[tuple[str, int]] = [
            (m.group(1).upper(), m.start())
            for m in self._DIVISION_RE.finditer(source)
        ]
        result: dict[str, list[str]] = {}
        for idx, (div_name, start) in enumerate(divisions_pos):
            end = divisions_pos[idx + 1][1] if idx + 1 < len(divisions_pos) else len(source)
            chunk = source[start:end]
            sections = [m.group(1) for m in self._SECTION_RE.finditer(chunk)]
            if sections:
                result[div_name] = sections
        return result

    def _extract_paragraphs_with_bodies(self, source: str) -> list[ParagraphDetail]:
        """Extract paragraph names AND their body lines from PROCEDURE DIVISION."""
        proc_match = re.search(
            r"PROCEDURE\s+DIVISION\s*\.", source, re.IGNORECASE,
        )
        if not proc_match:
            return []
        proc_text = source[proc_match.end():]
        lines = proc_text.splitlines()

        # First pass: find paragraph label positions
        para_positions: list[tuple[str, int]] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Paragraph label: starts in area A (column ~8), ends with "."
            # and is a single word followed by a period
            m = re.match(r"^(\w[\w-]*)\.\s*$", stripped)
            if m:
                name = m.group(1)
                if name.upper() not in self._KEYWORDS:
                    para_positions.append((name, i))

        # Second pass: extract body lines between paragraphs
        details: list[ParagraphDetail] = []
        for idx, (name, start_line) in enumerate(para_positions):
            if idx + 1 < len(para_positions):
                end_line = para_positions[idx + 1][1]
            else:
                end_line = len(lines)

            body = []
            for line in lines[start_line + 1 : end_line]:
                stripped = line.strip()
                if stripped and stripped != ".":
                    body.append(stripped)
            details.append(ParagraphDetail(name=name, body_lines=body))

        return details

    def _extract_data_items(self, source: str) -> list[DataItem]:
        """Extract data items including level-88 and REDEFINES."""
        items: list[DataItem] = []

        # Standard data items (level 01-49, 66, 77)
        for m in self._DATA_ITEM_RE.finditer(source):
            items.append(
                DataItem(
                    level=m.group(1),
                    name=m.group(2),
                    redefines=m.group(3) or "",
                    picture=m.group(4) or "",
                    value=(m.group(5) or "").strip().strip("'\""),
                )
            )

        # Level-88 boolean condition items
        for m in self._LEVEL_88_RE.finditer(source):
            items.append(
                DataItem(
                    level="88",
                    name=m.group(1),
                    value=m.group(2).strip().strip("'\""),
                    is_level_88=True,
                )
            )

        # Build hierarchy: nest sub-items under their parent group items
        items = self._build_hierarchy(items)

        return items

    @staticmethod
    def _build_hierarchy(flat_items: list[DataItem]) -> list[DataItem]:
        """Nest sub-level items under their parent group items.

        Group items are items with a level number (e.g. 01, 05) that have
        no PIC clause — they serve as containers for their children.
        """
        if not flat_items:
            return flat_items

        root_items: list[DataItem] = []
        stack: list[DataItem] = []

        for item in flat_items:
            try:
                lvl = int(item.level)
            except ValueError:
                root_items.append(item)
                continue

            # Pop stack until we find a parent with a lower level number
            while stack and int(stack[-1].level) >= lvl:
                stack.pop()

            if stack:
                stack[-1].children.append(item)
            else:
                root_items.append(item)

            # Items without PIC are group items — they can have children
            if not item.picture and not item.is_level_88:
                stack.append(item)

        return root_items

    # ------------------------------------------------------------------
    # Summary / prompt builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_flow_summary(analysis: StructureAnalysis) -> str:
        """Human-readable summary of the program structure."""
        lines = [f"Program: {analysis.program_id}"]
        lines.append(f"Divisions: {', '.join(analysis.divisions) or 'none detected'}")
        if analysis.sections:
            for div, secs in analysis.sections.items():
                lines.append(f"  {div} → sections: {', '.join(secs)}")
        if analysis.paragraphs:
            lines.append(f"Paragraphs: {', '.join(analysis.paragraphs)}")
        if analysis.paragraph_details:
            for pd in analysis.paragraph_details:
                line_count = len(pd.body_lines)
                lines.append(f"  {pd.name}: {line_count} statement(s)")
        data_count = sum(
            1 for d in analysis.data_items if not d.is_level_88
        )
        l88_count = sum(1 for d in analysis.data_items if d.is_level_88)
        if data_count:
            lines.append(f"Data items: {data_count} variables declared")
        if l88_count:
            lines.append(f"Level-88 items: {l88_count} boolean conditions")
        return "\n".join(lines)

    @staticmethod
    def _build_prompt(
        source: str,
        analysis: StructureAnalysis,
        context: dict[str, Any],
    ) -> str:
        """Construct a structured LLM prompt for refining the analysis."""
        rag_section = ""
        if context:
            rag_section = (
                "\n## Retrieved Context\n"
                + "\n".join(f"- {k}: {v}" for k, v in context.items())
            )

        para_bodies = ""
        if analysis.paragraph_details:
            parts = []
            for pd in analysis.paragraph_details:
                body = "\n".join(f"    {ln}" for ln in pd.body_lines)
                parts.append(f"  {pd.name}:\n{body}")
            para_bodies = "\n## Paragraph Bodies\n" + "\n".join(parts)

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
- Program ID: {analysis.program_id}
- Divisions : {', '.join(analysis.divisions)}
- Paragraphs: {', '.join(analysis.paragraphs) or 'none'}
- Data items: {len(analysis.data_items)}
{para_bodies}
{rag_section}

## Instructions
1. Confirm or correct the division/section/paragraph identification.
2. Describe the logical flow of the PROCEDURE DIVISION step-by-step.
3. Note any COPY or CALL dependencies.
4. Identify level-88 condition names and REDEFINES relationships.
5. Return your answer as structured JSON with keys:
   divisions, sections, paragraphs, paragraph_bodies, data_items, logical_flow.
"""


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sample = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYROLL.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT EMPLOYEE-FILE ASSIGN TO 'EMP.DAT'.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SALARY PIC 9(7)V99.
       01 WS-TAX    PIC 9(7)V99.
       01 WS-ACTIVE PIC X.
          88 IS-ACTIVE VALUE 'Y'.
          88 IS-INACTIVE VALUE 'N'.
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

    expert = StructureExpert()
    result = expert.run(sample)
    for key, value in result.items():
        if key != "prompt_payload":
            print(f"{key}: {value}")
    print("\n--- prompt payload (first 400 chars) ---")
    print(result["prompt_payload"][:400])
