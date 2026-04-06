"""Intelligent error diagnosis and fix-generation expert."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agents.base import BaseExpert
from config import ERROR_SEVERITY, Severity
from agents.prompts import DebugPrompt


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TracebackFrame:
    filename: str = ""
    line_number: int = 0
    function_name: str = ""
    code_line: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.filename, "line": self.line_number,
            "function": self.function_name, "code": self.code_line,
        }


@dataclass
class DebugResult:
    error_type: str = ""
    error_summary: str = ""
    severity: Severity = Severity.MODERATE
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
            "severity": self.severity.value,
            "traceback_frames": [f.to_dict() for f in self.traceback_frames],
            "offending_lines": self.offending_lines,
            "analysis": self.analysis,
            "root_cause": self.root_cause,
            "fix_suggestions": self.fix_suggestions,
            "corrected_code_prompt": self.corrected_code_prompt,
        }


# ---------------------------------------------------------------------------
# Expert
# ---------------------------------------------------------------------------

class DebugExpert(BaseExpert):
    """Diagnoses errors in generated Python and produces fix prompts."""

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

    _FRAME_RE = re.compile(r'File "([^"]+)", line (\d+), in (\w+)\n\s+(.+)')

    _COBOL_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
        (re.compile(r"name '(\w+)' is not defined"),
         "Untranslated COBOL data item or paragraph — '{0}' was referenced but not declared.", "missing"),
        (re.compile(r"Did you mean: '(\w+)'"),
         "Likely a typo during translation — Python suggests '{0}'.", "typo"),
        (re.compile(r"unsupported operand type.*'(\w+)'.*'(\w+)'"),
         "Type mismatch: PIC mapped to '{0}' but operation expects '{1}'.", "type"),
        (re.compile(r"can't multiply sequence"),
         "String used where number expected — PIC A/X field in arithmetic.", "type"),
        (re.compile(r"local variable '(\w+)' referenced before assignment"),
         "Missing 'global' declaration — '{0}' needs global statement.", "scope"),
        (re.compile(r"division by zero"),
         "COBOL DIVIDE has no zero-guard — divisor not initialised.", "arithmetic"),
        (re.compile(r"invalid literal for int"),
         "ACCEPT input not cast to correct numeric type.", "cast"),
        (re.compile(r"index out of range"),
         "COBOL 1-based vs Python 0-based indexing — off-by-one.", "indexing"),
    ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        python_code: str = "",
        error_message: str = "",
        cobol_source: str = "",
        context: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        """Analyse an error and produce debugging guidance + fix prompt."""
        ctx = self.validate_context(context)
        result = DebugResult()

        result.error_type, result.error_summary = self._classify(error_message)
        result.traceback_frames = self._parse_traceback(error_message)
        result.offending_lines = self._extract_offending(python_code, result.traceback_frames)
        result.analysis = self._analyse(result.error_type, result.error_summary,
                                        python_code, result.traceback_frames)
        result.root_cause = self._root_cause(error_message, result.error_summary, cobol_source)
        result.fix_suggestions = self._suggest_fixes(result.error_type, error_message,
                                                     python_code, cobol_source)
        result.severity = self._compute_severity(result.error_type, result.root_cause)
        result.corrected_code_prompt = DebugPrompt.build(
            code=python_code, error=error_message, cobol_source=cobol_source,
            error_type=result.error_type, error_summary=result.error_summary,
            severity=result.severity.value, root_cause=result.root_cause,
            analysis=result.analysis, fix_suggestions=result.fix_suggestions,
            traceback_frames=[f.to_dict() for f in result.traceback_frames],
            offending_lines=result.offending_lines, context=ctx,
        )

        self.logger.debug("Diagnosed %s (severity %s)", result.error_type, result.severity.label)
        return result.to_dict()

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify(self, msg: str) -> tuple[str, str]:
        for etype, pat in self._ERROR_PATTERNS:
            m = pat.search(msg)
            if m:
                return etype, m.group(1).strip()
        first = msg.strip().splitlines()[0] if msg.strip() else "Unknown error"
        return "LogicError", first

    # ------------------------------------------------------------------
    # Traceback parsing
    # ------------------------------------------------------------------

    def _parse_traceback(self, msg: str) -> list[TracebackFrame]:
        return [
            TracebackFrame(m.group(1), int(m.group(2)), m.group(3), m.group(4).strip())
            for m in self._FRAME_RE.finditer(msg)
        ]

    # ------------------------------------------------------------------
    # Offending lines
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_offending(code: str, frames: list[TracebackFrame]) -> list[dict[str, Any]]:
        code_lines = code.splitlines()
        result: list[dict[str, Any]] = []
        seen: set[int] = set()
        for f in frames:
            ln = f.line_number
            if 1 <= ln <= len(code_lines) and ln not in seen:
                seen.add(ln)
                s, e = max(0, ln - 3), min(len(code_lines), ln + 2)
                result.append({
                    "line_number": ln,
                    "line": code_lines[ln - 1].rstrip(),
                    "context": [
                        f"{'→' if i + 1 == ln else ' '} {i + 1:4d} | {code_lines[i].rstrip()}"
                        for i in range(s, e)
                    ],
                })
        return result

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    @staticmethod
    def _analyse(etype: str, summary: str, code: str, frames: list[TracebackFrame]) -> str:
        code_lines = code.strip().splitlines()
        parts = [
            f"Error type  : {etype}",
            f"Summary     : {summary}",
            f"Code size   : {len(code_lines)} lines",
            f"Stack depth : {len(frames)} frame(s)",
        ]
        if frames:
            last = frames[-1]
            parts.append(f"Origin      : {last.function_name}() at line {last.line_number}")
            parts.append(f"Statement   : {last.code_line}")
        if etype == "NameError":
            nm = re.search(r"name '(\w+)'", summary)
            if nm:
                parts.append(f"Missing name: '{nm.group(1)}'")
                close = [n for n in set(re.findall(r"\b\w+\b", code))
                         if n != nm.group(1) and _similarity(n, nm.group(1)) > 0.7]
                if close:
                    parts.append(f"  → Similar: {', '.join(sorted(close)[:5])}")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Root cause
    # ------------------------------------------------------------------

    def _root_cause(self, error: str, summary: str, cobol: str) -> str:
        combined = f"{error}\n{summary}"
        for pat, tmpl, cat in self._COBOL_PATTERNS:
            m = pat.search(combined)
            if m:
                cause = tmpl.format(*m.groups())
                if cobol and cat == "missing":
                    cobol_name = (m.group(1) if m.lastindex else "").upper().replace("_", "-")
                    if cobol_name in cobol.upper():
                        cause += f"\n  → '{cobol_name}' exists in COBOL but was not translated."
                return cause
        return "No specific COBOL-related root cause identified."

    # ------------------------------------------------------------------
    # Fix suggestions
    # ------------------------------------------------------------------

    def _suggest_fixes(self, etype: str, error: str, code: str, cobol: str) -> list[str]:
        suggestions: list[str] = []
        if etype == "NameError":
            nm = re.search(r"name '(\w+)'", error)
            if nm:
                suggestions.append(f"Add declaration for '{nm.group(1)}'.")
                hint = re.search(r"Did you mean: '(\w+)'", error)
                if hint:
                    suggestions.append(f"Fix typo: '{nm.group(1)}' → '{hint.group(1)}'.")
                if "global" not in code:
                    suggestions.append(f"Add 'global {nm.group(1)}' in the function.")
        elif etype in ("SyntaxError", "IndentationError"):
            suggestions.append("Check for missing colons / balanced brackets.")
            if "indent" in error.lower():
                suggestions.append("Ensure consistent 4-space indentation.")
        elif etype == "TypeError":
            suggestions.append("Check PIC-to-type mapping (numeric PIC → int or Decimal).")
            if "Decimal" in code:
                suggestions.append("Don't mix Decimal with float literals.")
        elif etype == "ZeroDivisionError":
            suggestions.append("Add zero-guard before DIVIDE.")
            dm = re.search(r"DIVIDE\s+(\w[\w-]*)\s+INTO", cobol, re.I)
            if dm:
                suggestions.append(f"Ensure '{dm.group(1)}' is non-zero.")
        elif etype == "LogicError":
            suggestions.append("Verify PERFORM UNTIL condition is inverted.")
            suggestions.append("Check EVALUATE/WHEN coverage.")
        if not suggestions:
            suggestions.append("Review COBOL source for unmapped constructs.")
        suggestions.append("Cross-reference with original COBOL logic.")
        return suggestions

    # ------------------------------------------------------------------
    # Severity
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_severity(etype: str, cause: str) -> Severity:
        base = ERROR_SEVERITY.get(etype, Severity.MODERATE).value
        if "scope" in cause.lower():
            base = min(base, 2)
        if "logic" in etype.lower():
            base = max(base, 4)
        return Severity(max(1, min(5, base)))


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    la, lb = a.lower(), b.lower()
    ba = {la[i:i + 2] for i in range(len(la) - 1)}
    bb = {lb[i:i + 2] for i in range(len(lb) - 1)}
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / len(ba | bb)
