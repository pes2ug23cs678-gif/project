"""
router.py — Task complexity classifier and expert routing.

The Router inspects incoming COBOL source code, scores its structural
complexity using lightweight heuristics, and returns routing metadata
that tells the AgentController which pipeline flow to use.

Complexity is scored across four dimensions:
  1. Division count (IDENTIFICATION, ENVIRONMENT, DATA, PROCEDURE)
  2. PERFORM nesting depth (loops / paragraph calls)
  3. External references (COPY, CALL)
  4. Line count

A composite score maps to "simple" or "complex", which determines
whether the controller runs the abbreviated or full expert pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Complexity thresholds (tunable)
# ---------------------------------------------------------------------------
_DIVISION_WEIGHT = 1.0
_PERFORM_WEIGHT = 2.0
_EXTERNAL_WEIGHT = 3.0
_LINE_COUNT_WEIGHT = 0.01
_COMPLEXITY_THRESHOLD = 6.0  # score >= this ⇒ "complex"


@dataclass
class RoutingResult:
    """Structured output returned by the Router."""

    complexity: str                   # "simple" | "complex"
    score: float                      # raw composite score
    dimensions: dict[str, Any] = field(default_factory=dict)
    recommended_flow: list[str] = field(default_factory=list)


class Router:
    """Rule-based classifier that determines task complexity and routing."""

    def __init__(
        self,
        complexity_threshold: float = _COMPLEXITY_THRESHOLD,
    ) -> None:
        self.complexity_threshold = complexity_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, task_input: dict[str, Any]) -> RoutingResult:
        """Analyse *task_input* and return a :class:`RoutingResult`.

        Parameters
        ----------
        task_input : dict
            Must contain at least ``"cobol_source"`` (str).
            Optionally ``"context"`` (dict) with RAG-retrieved data.

        Returns
        -------
        RoutingResult
            Contains complexity label, numeric score, dimension breakdown,
            and the recommended expert flow.
        """
        source: str = task_input.get("cobol_source", "")
        dimensions = self._score_dimensions(source)
        score = self._composite_score(dimensions)
        complexity = "complex" if score >= self.complexity_threshold else "simple"
        flow = self._recommended_flow(complexity)

        return RoutingResult(
            complexity=complexity,
            score=round(score, 2),
            dimensions=dimensions,
            recommended_flow=flow,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_dimensions(source: str) -> dict[str, Any]:
        """Extract quantitative dimensions from raw COBOL source."""
        upper = source.upper()
        lines = [ln.strip() for ln in upper.splitlines() if ln.strip()]

        # 1. Count standard divisions
        division_pattern = re.compile(
            r"\b(IDENTIFICATION|ENVIRONMENT|DATA|PROCEDURE)\s+DIVISION"
        )
        divisions_found = list({m.group(1) for m in division_pattern.finditer(upper)})

        # 2. PERFORM statements (proxy for control-flow complexity)
        perform_count = len(re.findall(r"\bPERFORM\b", upper))

        # 3. External references: COPY and CALL
        copy_count = len(re.findall(r"\bCOPY\b", upper))
        call_count = len(re.findall(r"\bCALL\b", upper))

        # 4. Gross line count
        line_count = len(lines)

        return {
            "divisions": divisions_found,
            "division_count": len(divisions_found),
            "perform_count": perform_count,
            "copy_count": copy_count,
            "call_count": call_count,
            "line_count": line_count,
        }

    @staticmethod
    def _composite_score(dims: dict[str, Any]) -> float:
        """Compute a weighted composite complexity score."""
        return (
            dims["division_count"] * _DIVISION_WEIGHT
            + dims["perform_count"] * _PERFORM_WEIGHT
            + (dims["copy_count"] + dims["call_count"]) * _EXTERNAL_WEIGHT
            + dims["line_count"] * _LINE_COUNT_WEIGHT
        )

    @staticmethod
    def _recommended_flow(complexity: str) -> list[str]:
        """Return the ordered list of experts for the given complexity."""
        if complexity == "simple":
            # Skip deep structural analysis for trivial programs
            return ["translation_expert", "test_expert"]
        return [
            "structure_expert",
            "translation_expert",
            "test_expert",
        ]


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sample_cobol = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELLO-WORLD.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-NAME PIC A(20).
       PROCEDURE DIVISION.
           DISPLAY 'HELLO WORLD'.
           STOP RUN.
    """

    router = Router()
    result = router.classify({"cobol_source": sample_cobol})
    print(f"Complexity : {result.complexity}")
    print(f"Score      : {result.score}")
    print(f"Dimensions : {result.dimensions}")
    print(f"Flow       : {result.recommended_flow}")
