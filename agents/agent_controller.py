"""Pipeline orchestrator for the COBOL-to-Python multi-agent system."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from config import Complexity, PipelineConfig
from agents.router import Router, RoutingResult
from agents.structure_expert import StructureExpert
from agents.translation_expert import TranslationExpert
from agents.debug_expert import DebugExpert
from agents.test_expert import TestExpert

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------

@dataclass
class PipelineState:
    """Mutable state passed through the pipeline stages."""

    cobol_source: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    routing: RoutingResult | None = None
    structure: dict[str, Any] = field(default_factory=dict)
    translation: dict[str, Any] = field(default_factory=dict)
    tests: dict[str, Any] = field(default_factory=dict)
    debug_history: list[dict[str, Any]] = field(default_factory=list)
    error_message: str = ""
    iteration: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "routing": {
                "complexity": self.routing.complexity.value if self.routing else "",
                "score": self.routing.score if self.routing else 0,
                "dimensions": self.routing.dimensions if self.routing else {},
                "recommended_flow": self.routing.recommended_flow if self.routing else [],
            },
            "structure": self.structure,
            "translation": self.translation,
            "tests": self.tests,
            "debug_history": self.debug_history,
            "iterations": self.iteration,
        }


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class AgentController:
    """Orchestrates the COBOL-to-Python migration pipeline.

    Parameters
    ----------
    config : PipelineConfig, optional
        Top-level configuration.

    Usage
    -----
    >>> controller = AgentController()
    >>> result = controller.run(cobol_source=src)
    >>> print(result["translation"]["python_code"])
    """

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self._config = config or PipelineConfig()
        self.router = Router()
        self.structure_expert = StructureExpert()
        self.translation_expert = TranslationExpert()
        self.debug_expert = DebugExpert()
        self.test_expert = TestExpert()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        cobol_source: str,
        context: dict[str, Any] | None = None,
        error_message: str = "",
    ) -> dict[str, Any]:
        """Execute the full migration pipeline.

        Raises
        ------
        ValueError
            If *cobol_source* is empty.
        """
        if not cobol_source or not cobol_source.strip():
            raise ValueError("cobol_source must not be empty")

        state = PipelineState(
            cobol_source=cobol_source,
            context=context or {},
            error_message=error_message,
        )

        state = self._step_route(state)
        logger.info("Routed: %s (score=%.2f)", state.routing.complexity.value, state.routing.score)

        if "structure_expert" in (state.routing.recommended_flow or []):
            state = self._step_structure(state)
            logger.info("Structure: %s", state.structure.get("program_id"))

        state = self._step_translate(state)
        logger.info("Translation: %d chars", len(state.translation.get("python_code", "")))

        if state.error_message:
            state = self._debug_loop(state)

        state = self._step_test(state)
        logger.info("Tests: %d cases", len(state.tests.get("test_cases", [])))

        return state.to_dict()

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def _step_route(self, state: PipelineState) -> PipelineState:
        state.routing = self.router.classify({
            "cobol_source": state.cobol_source,
            "context": state.context,
        })
        return state

    def _step_structure(self, state: PipelineState) -> PipelineState:
        state.structure = self.structure_expert.run(
            cobol_source=state.cobol_source, context=state.context,
        )
        return state

    def _step_translate(self, state: PipelineState) -> PipelineState:
        structure = state.structure or {
            "program_id": "UNKNOWN", "divisions": [], "sections": {},
            "paragraphs": [], "paragraph_details": [], "data_items": [],
            "flow_summary": "",
        }
        state.translation = self.translation_expert.run(
            structure_analysis=structure,
            cobol_source=state.cobol_source,
            context=state.context,
        )
        state.iteration += 1
        return state

    def _step_test(self, state: PipelineState) -> PipelineState:
        state.tests = self.test_expert.run(
            python_code=state.translation.get("python_code", ""),
            cobol_source=state.cobol_source,
            structure_analysis=state.structure,
            context=state.context,
        )
        return state

    def _debug_loop(self, state: PipelineState) -> PipelineState:
        retries = 0
        max_retries = self._config.max_debug_retries

        while state.error_message and retries < max_retries:
            retries += 1
            logger.info("Debug %d/%d", retries, max_retries)

            debug_result = self.debug_expert.run(
                python_code=state.translation.get("python_code", ""),
                error_message=state.error_message,
                cobol_source=state.cobol_source,
                context=state.context,
            )
            state.debug_history.append({
                "iteration": retries,
                "error_type": debug_result["error_type"],
                "error_summary": debug_result["error_summary"],
                "severity": debug_result.get("severity", 0),
                "root_cause": debug_result.get("root_cause", ""),
                "traceback_frames": debug_result.get("traceback_frames", []),
                "offending_lines": debug_result.get("offending_lines", []),
                "fix_suggestions": debug_result["fix_suggestions"],
            })
            state.translation["debug_prompt"] = debug_result["corrected_code_prompt"]
            state.error_message = ""
            state.iteration += 1

        if state.error_message:
            logger.warning("Debug retries exhausted: %s", state.error_message)
            state.debug_history.append({
                "iteration": retries + 1,
                "status": "RETRIES_EXHAUSTED",
                "remaining_error": state.error_message,
            })
        return state
