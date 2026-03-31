"""
structure_expert.py — COBOL structure analysis expert.

Parses raw COBOL source into a structural map:
  • Divisions (IDENTIFICATION, ENVIRONMENT, DATA, PROCEDURE)
  • Sections within each division
  • Paragraphs within PROCEDURE DIVISION
  • Data items from DATA DIVISION (level numbers + PIC clauses)
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

    def to_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "name": self.name,
            "picture": self.picture,
            "value": self.value,
        }


@dataclass
class StructureAnalysis:
    """Complete structural breakdown of a COBOL program."""

    program_id: str = ""
    divisions: list[str] = field(default_factory=list)
    sections: dict[str, list[str]] = field(default_factory=dict)
    paragraphs: list[str] = field(default_factory=list)
    data_items: list[DataItem] = field(default_factory=list)
    flow_summary: str = ""
    prompt_payload: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "divisions": self.divisions,
            "sections": {k: v for k, v in self.sections.items()},
            "paragraphs": self.paragraphs,
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
        r"(?:\s+PIC(?:TURE)?\s+([\w\(\)\.]+))?"
        r"(?:\s+VALUE\s+(.+?))?\s*\.",
        re.MULTILINE | re.IGNORECASE,
    )

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
            data_items, flow_summary, prompt_payload.
        """
        context = context or {}
        analysis = StructureAnalysis()

        analysis.program_id = self._extract_program_id(cobol_source)
        analysis.divisions = self._extract_divisions(cobol_source)
        analysis.sections = self._extract_sections(cobol_source)
        analysis.paragraphs = self._extract_paragraphs(cobol_source)
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

    def _extract_paragraphs(self, source: str) -> list[str]:
        """Extract paragraph names from the PROCEDURE DIVISION."""
        proc_match = re.search(
            r"PROCEDURE\s+DIVISION\s*\.", source, re.IGNORECASE,
        )
        if not proc_match:
            return []
        proc_text = source[proc_match.end():]
        # Paragraphs are labels starting in column 8 (area A)
        candidates = self._PARAGRAPH_RE.findall(proc_text)
        # Filter out COBOL keywords that look like paragraphs
        keywords = {
            "STOP", "DISPLAY", "MOVE", "PERFORM", "IF", "ELSE",
            "END-IF", "EVALUATE", "END-EVALUATE", "ACCEPT", "ADD",
            "SUBTRACT", "MULTIPLY", "DIVIDE", "COMPUTE", "GO",
            "OPEN", "READ", "WRITE", "CLOSE", "CALL",
        }
        return [p for p in candidates if p.upper() not in keywords]

    def _extract_data_items(self, source: str) -> list[DataItem]:
        """Extract level-number / name / PIC / VALUE from DATA DIVISION."""
        items: list[DataItem] = []
        for m in self._DATA_ITEM_RE.finditer(source):
            items.append(
                DataItem(
                    level=m.group(1),
                    name=m.group(2),
                    picture=m.group(3) or "",
                    value=(m.group(4) or "").strip().strip("'\""),
                )
            )
        return items

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
        if analysis.data_items:
            lines.append(f"Data items: {len(analysis.data_items)} variables declared")
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
{rag_section}

## Instructions
1. Confirm or correct the division/section/paragraph identification.
2. Describe the logical flow of the PROCEDURE DIVISION step-by-step.
3. Note any COPY or CALL dependencies.
4. Return your answer as structured JSON with keys:
   divisions, sections, paragraphs, data_items, logical_flow.
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
    print("\n--- prompt payload (first 300 chars) ---")
    print(result["prompt_payload"][:300])
