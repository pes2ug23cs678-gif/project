"""Pipeline orchestrator for the COBOL-to-Python multi-agent system.

This module provides the ``AgentController`` class, which coordinates the
full migration pipeline: routing → structure analysis → translation →
debug loop → test generation.

Usage
-----
>>> controller = AgentController()
>>> result = controller.run(cobol_source=src)
>>> print(result["translation"]["python_code"])
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from config import PipelineConfig
from agents.router import classify as route_classify
from agents.structure_expert import StructureExpert
from agents.translation_expert import generate_python
from agents.debug_expert import fix_code
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
    routing: dict[str, Any] = field(default_factory=dict)
    structure: dict[str, Any] = field(default_factory=dict)
    translation: dict[str, Any] = field(default_factory=dict)
    tests: dict[str, Any] = field(default_factory=dict)
    debug_history: list[dict[str, Any]] = field(default_factory=list)
    error_message: str = ""
    iteration: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "routing": self.routing,
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
    """

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self._config = config or PipelineConfig()
        self.structure_expert = StructureExpert()
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
        route = state.routing.get("complexity", "simple")
        logger.info("Routed: %s", route)

        if route == "complex":
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
        route = route_classify(state.cobol_source)
        state.routing = {
            "complexity": route,
            "score": 1.0 if route == "complex" else 0.0,
            "dimensions": {},
            "recommended_flow": (
                ["structure_expert", "translation_expert", "debug_expert"]
                if route == "complex"
                else ["translation_expert"]
            ),
        }
        return state

    def _step_structure(self, state: PipelineState) -> PipelineState:
        state.structure = self.structure_expert.run(
            cobol_source=state.cobol_source, context=state.context,
        )
        return state

    def _step_translate(self, state: PipelineState) -> PipelineState:
        python_code = generate_python(
            cobol_code=state.cobol_source,
            structured_analysis=state.structure or None,
        )
        state.translation = {"python_code": python_code}
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

            fixed = fix_code(
                broken_code=state.translation.get("python_code", ""),
                error_type="runtime",
                stderr=state.error_message,
                stdout="",
            )
            state.debug_history.append({
                "iteration": retries,
                "error_type": "runtime",
                "error_summary": state.error_message[:200],
                "severity": 3,
            })
            state.translation["python_code"] = fixed
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
