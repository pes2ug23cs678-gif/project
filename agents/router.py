"""Rule-based task complexity classifier and expert routing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agents.config import Complexity, RouterConfig


@dataclass
class RoutingResult:
    """Structured output returned by the Router."""

    complexity: Complexity
    score: float
    dimensions: dict[str, Any] = field(default_factory=dict)
    recommended_flow: list[str] = field(default_factory=list)


class Router:
    """Classifies COBOL source complexity and selects the expert pipeline.

    Parameters
    ----------
    config : RouterConfig, optional
        Tunable weights and threshold.  Defaults to standard values.
    """

    _SIMPLE_FLOW = ["translation_expert", "test_expert"]
    _COMPLEX_FLOW = ["structure_expert", "translation_expert", "test_expert"]

    def __init__(self, config: RouterConfig | None = None) -> None:
        self.config = config or RouterConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, task_input: dict[str, Any]) -> RoutingResult:
        """Analyse *task_input* and return a :class:`RoutingResult`.

        Parameters
        ----------
        task_input : dict
            Must contain ``"cobol_source"`` (str).

        Raises
        ------
        ValueError
            If ``cobol_source`` is missing or empty.
        """
        source: str = task_input.get("cobol_source", "")
        if not source.strip():
            raise ValueError("task_input must contain a non-empty 'cobol_source'")

        dimensions = self._score_dimensions(source)
        score = self._composite_score(dimensions)
        complexity = (
            Complexity.COMPLEX
            if score >= self.config.complexity_threshold
            else Complexity.SIMPLE
        )
        flow = (
            list(self._COMPLEX_FLOW)
            if complexity is Complexity.COMPLEX
            else list(self._SIMPLE_FLOW)
        )

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
        upper = source.upper()
        lines = [ln for ln in upper.splitlines() if ln.strip()]

        division_re = re.compile(
            r"\b(IDENTIFICATION|ENVIRONMENT|DATA|PROCEDURE)\s+DIVISION",
        )
        divisions_found = sorted({m.group(1) for m in division_re.finditer(upper)})

        return {
            "divisions": divisions_found,
            "division_count": len(divisions_found),
            "perform_count": len(re.findall(r"\bPERFORM\b", upper)),
            "copy_count": len(re.findall(r"\bCOPY\b", upper)),
            "call_count": len(re.findall(r"\bCALL\b", upper)),
            "line_count": len(lines),
        }

    def _composite_score(self, dims: dict[str, Any]) -> float:
        cfg = self.config
        return (
            dims["division_count"] * cfg.division_weight
            + dims["perform_count"] * cfg.perform_weight
            + (dims["copy_count"] + dims["call_count"]) * cfg.external_weight
            + dims["line_count"] * cfg.line_count_weight
        )
