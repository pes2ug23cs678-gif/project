"""
agent_controller.py — Pipeline orchestrator for the multi-agent system.

The AgentController wires together Router → Experts in the correct
sequence, passes structured data between stages, and optionally loops
through the DebugExpert when errors are detected.

Two pipeline flows:
  • simple  — TranslationExpert → TestExpert
  • complex — StructureExpert → TranslationExpert → TestExpert

If an error message is supplied (or detected), the controller invokes
the DebugExpert and re-runs translation (up to *max_debug_retries*).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agents.router import Router, RoutingResult
from agents.structure_expert import StructureExpert
from agents.translation_expert import TranslationExpert
from agents.debug_expert import DebugExpert
from agents.test_expert import TestExpert

logger = logging.getLogger(__name__)


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
                "complexity": self.routing.complexity if self.routing else "",
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


class AgentController:
    """Orchestrates the COBOL-to-Python migration pipeline.

    Usage
    -----
    >>> controller = AgentController()
    >>> result = controller.run(cobol_source=src, context=rag_context)
    >>> print(result["translation"]["python_code"])
    """

    def __init__(self, max_debug_retries: int = 3) -> None:
        self.max_debug_retries = max_debug_retries

        # Instantiate all components
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

        Parameters
        ----------
        cobol_source : str
            Raw COBOL source code.
        context : dict, optional
            RAG-retrieved context (domain knowledge, coding patterns).
        error_message : str, optional
            If provided, the pipeline starts in debug mode, using the
            error to drive a fix-and-retry loop.

        Returns
        -------
        dict
            Complete pipeline result with keys:
            routing, structure, translation, tests, debug_history, iterations.
        """
        state = PipelineState(
            cobol_source=cobol_source,
            context=context or {},
            error_message=error_message,
        )

        # Step 1 — Route
        state = self._step_route(state)
        logger.info(
            "Routing complete: complexity=%s, score=%s, flow=%s",
            state.routing.complexity,
            state.routing.score,
            state.routing.recommended_flow,
        )

        # Step 2 — Structure analysis (complex flow only)
        if "structure_expert" in (state.routing.recommended_flow or []):
            state = self._step_structure(state)
            logger.info("Structure analysis complete for %s", state.structure.get("program_id"))

        # Step 3 — Translation
        state = self._step_translate(state)
        logger.info("Initial translation generated (%d chars)", len(state.translation.get("python_code", "")))

        # Step 4 — Debug loop (if error_message was provided or detected)
        if state.error_message:
            state = self._debug_loop(state)

        # Step 5 — Test generation
        state = self._step_test(state)
        logger.info("Test generation complete (%d cases)", len(state.tests.get("test_cases", [])))

        return state.to_dict()

    # ------------------------------------------------------------------
    # Pipeline step: Routing
    # ------------------------------------------------------------------

    def _step_route(self, state: PipelineState) -> PipelineState:
        """Classify input complexity and determine expert flow."""
        result = self.router.classify({
            "cobol_source": state.cobol_source,
            "context": state.context,
        })
        state.routing = result
        return state

    # ------------------------------------------------------------------
    # Pipeline step: Structure analysis
    # ------------------------------------------------------------------

    def _step_structure(self, state: PipelineState) -> PipelineState:
        """Parse COBOL source into a structural map."""
        state.structure = self.structure_expert.run(
            cobol_source=state.cobol_source,
            context=state.context,
        )
        return state

    # ------------------------------------------------------------------
    # Pipeline step: Translation
    # ------------------------------------------------------------------

    def _step_translate(self, state: PipelineState) -> PipelineState:
        """Generate Python translation from structure + COBOL source."""
        # If no structure analysis was done (simple flow), provide a
        # minimal structure dict so the translation expert still works.
        structure = state.structure or {
            "program_id": "UNKNOWN",
            "divisions": [],
            "sections": {},
            "paragraphs": [],
            "data_items": [],
            "flow_summary": "",
        }
        state.translation = self.translation_expert.run(
            structure_analysis=structure,
            cobol_source=state.cobol_source,
            context=state.context,
        )
        state.iteration += 1
        return state

    # ------------------------------------------------------------------
    # Pipeline step: Debug loop
    # ------------------------------------------------------------------

    def _debug_loop(self, state: PipelineState) -> PipelineState:
        """Iteratively debug until error is resolved or retries exhausted."""
        retries = 0
        while state.error_message and retries < self.max_debug_retries:
            retries += 1
            logger.info("Debug iteration %d/%d", retries, self.max_debug_retries)

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

            # In a real system the corrected_code_prompt would be sent
            # to an LLM and the response would replace python_code.
            # Here we store the prompt so the execution layer can use it.
            state.translation["debug_prompt"] = debug_result["corrected_code_prompt"]

            # Clear the error — in a real loop the execution layer would
            # re-run the code and set a new error_message if it fails again.
            state.error_message = ""
            state.iteration += 1

        if state.error_message:
            logger.warning("Debug retries exhausted — error persists: %s", state.error_message)
            state.debug_history.append({
                "iteration": retries + 1,
                "status": "RETRIES_EXHAUSTED",
                "remaining_error": state.error_message,
            })

        return state

    # ------------------------------------------------------------------
    # Pipeline step: Test generation
    # ------------------------------------------------------------------

    def _step_test(self, state: PipelineState) -> PipelineState:
        """Generate test cases for the translated Python code."""
        state.tests = self.test_expert.run(
            python_code=state.translation.get("python_code", ""),
            cobol_source=state.cobol_source,
            structure_analysis=state.structure,
            context=state.context,
        )
        return state


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    sample_cobol = """\
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

    controller = AgentController()

    # --- Normal flow ---
    print("=" * 60)
    print("NORMAL PIPELINE RUN")
    print("=" * 60)
    result = controller.run(cobol_source=sample_cobol, context={})
    print(f"\nRouting   : {result['routing']['complexity']} (score {result['routing']['score']})")
    print(f"Structure : program={result['structure'].get('program_id', 'N/A')}")
    print(f"Translation: {len(result['translation'].get('python_code', ''))} chars")
    print(f"Tests     : {len(result['tests'].get('test_cases', []))} cases")
    print(f"Iterations: {result['iterations']}")

    # --- Debug flow ---
    print("\n" + "=" * 60)
    print("DEBUG PIPELINE RUN")
    print("=" * 60)
    result = controller.run(
        cobol_source=sample_cobol,
        context={},
        error_message="NameError: name 'ws_salry' is not defined",
    )
    print(f"\nDebug history: {len(result['debug_history'])} entries")
    for entry in result["debug_history"]:
        print(f"  iter {entry.get('iteration')}: {entry.get('error_type', 'N/A')} — {entry.get('error_summary', 'N/A')}")
    print(f"Iterations: {result['iterations']}")
