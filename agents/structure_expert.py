"""COBOL structure analysis expert — parses source into a structural map."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agents.base import BaseExpert
from config import COBOL_KEYWORDS
from agents.prompts import StructurePrompt


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

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
    """Paragraph name together with its raw COBOL body lines."""

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
            "sections": dict(self.sections),
            "paragraphs": self.paragraphs,
            "paragraph_details": [p.to_dict() for p in self.paragraph_details],
            "data_items": [d.to_dict() for d in self.data_items],
            "flow_summary": self.flow_summary,
            "prompt_payload": self.prompt_payload,
        }


# ---------------------------------------------------------------------------
# Expert
# ---------------------------------------------------------------------------

class StructureExpert(BaseExpert):
    """Parses COBOL source code and produces a structured analysis."""

    _DIVISION_RE = re.compile(
        r"^\s*(\w[\w-]*)\s+DIVISION\s*\.", re.MULTILINE | re.IGNORECASE,
    )
    _SECTION_RE = re.compile(
        r"^\s*(\w[\w-]*)\s+SECTION\s*\.", re.MULTILINE | re.IGNORECASE,
    )
    _PROGRAM_ID_RE = re.compile(r"PROGRAM-ID\.\s*(\w[\w-]*)", re.IGNORECASE)
    _PARAGRAPH_LABEL_RE = re.compile(r"^(\w[\w-]*)\.\s*$")
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        cobol_source: str = "",
        context: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        """Analyse *cobol_source* and return a structural map."""
        source = self.validate_source(cobol_source)
        ctx = self.validate_context(context)

        analysis = StructureAnalysis()
        analysis.program_id = self._extract_program_id(source)
        analysis.divisions = self._extract_divisions(source)
        analysis.sections = self._extract_sections(source)

        details = self._extract_paragraphs_with_bodies(source)
        analysis.paragraphs = [p.name for p in details]
        analysis.paragraph_details = details

        analysis.data_items = self._extract_data_items(source)
        analysis.flow_summary = self._build_flow_summary(analysis)
        analysis.prompt_payload = StructurePrompt.build(
            source=source,
            program_id=analysis.program_id,
            divisions=analysis.divisions,
            paragraphs=analysis.paragraphs,
            paragraph_details=[p.to_dict() for p in analysis.paragraph_details],
            data_items=[d.to_dict() for d in analysis.data_items],
            context=ctx,
        )

        self.logger.debug("Parsed %s: %d paragraphs, %d data items",
                          analysis.program_id, len(analysis.paragraphs),
                          len(analysis.data_items))
        return analysis.to_dict()

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _extract_program_id(self, source: str) -> str:
        m = self._PROGRAM_ID_RE.search(source)
        return m.group(1) if m else "UNKNOWN"

    def _extract_divisions(self, source: str) -> list[str]:
        return [m.group(1).upper() for m in self._DIVISION_RE.finditer(source)]

    def _extract_sections(self, source: str) -> dict[str, list[str]]:
        positions = [
            (m.group(1).upper(), m.start())
            for m in self._DIVISION_RE.finditer(source)
        ]
        result: dict[str, list[str]] = {}
        for idx, (name, start) in enumerate(positions):
            end = positions[idx + 1][1] if idx + 1 < len(positions) else len(source)
            secs = [m.group(1) for m in self._SECTION_RE.finditer(source[start:end])]
            if secs:
                result[name] = secs
        return result

    def _extract_paragraphs_with_bodies(self, source: str) -> list[ParagraphDetail]:
        proc = re.search(r"PROCEDURE\s+DIVISION\s*\.", source, re.IGNORECASE)
        if not proc:
            return []

        lines = source[proc.end():].splitlines()
        positions: list[tuple[str, int]] = []
        for i, line in enumerate(lines):
            m = self._PARAGRAPH_LABEL_RE.match(line.strip())
            if m and m.group(1).upper() not in COBOL_KEYWORDS:
                positions.append((m.group(1), i))

        details: list[ParagraphDetail] = []
        for idx, (name, start) in enumerate(positions):
            end = positions[idx + 1][1] if idx + 1 < len(positions) else len(lines)
            body = [ln.strip() for ln in lines[start + 1:end] if ln.strip() and ln.strip() != "."]
            details.append(ParagraphDetail(name=name, body_lines=body))
        return details

    def _extract_data_items(self, source: str) -> list[DataItem]:
        items: list[DataItem] = []
        for m in self._DATA_ITEM_RE.finditer(source):
            items.append(DataItem(
                level=m.group(1),
                name=m.group(2),
                redefines=m.group(3) or "",
                picture=m.group(4) or "",
                value=(m.group(5) or "").strip().strip("'\""),
            ))
        for m in self._LEVEL_88_RE.finditer(source):
            items.append(DataItem(
                level="88", name=m.group(1),
                value=m.group(2).strip().strip("'\""),
                is_level_88=True,
            ))
        return self._build_hierarchy(items)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_hierarchy(flat: list[DataItem]) -> list[DataItem]:
        roots: list[DataItem] = []
        stack: list[DataItem] = []
        for item in flat:
            try:
                lvl = int(item.level)
            except ValueError:
                roots.append(item)
                continue
            while stack and int(stack[-1].level) >= lvl:
                stack.pop()
            (stack[-1].children if stack else roots).append(item)
            if not item.picture and not item.is_level_88:
                stack.append(item)
        return roots

    @staticmethod
    def _build_flow_summary(a: StructureAnalysis) -> str:
        parts = [f"Program: {a.program_id}"]
        parts.append(f"Divisions: {', '.join(a.divisions) or 'none detected'}")
        for div, secs in a.sections.items():
            parts.append(f"  {div} → {', '.join(secs)}")
        if a.paragraph_details:
            for pd in a.paragraph_details:
                parts.append(f"  {pd.name}: {len(pd.body_lines)} stmt(s)")
        data_count = sum(1 for d in a.data_items if not d.is_level_88)
        l88_count = sum(1 for d in a.data_items if d.is_level_88)
        if data_count:
            parts.append(f"Data items: {data_count}")
        if l88_count:
            parts.append(f"Level-88: {l88_count}")
        return "\n".join(parts)
