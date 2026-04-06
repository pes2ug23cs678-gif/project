"""Main integration layer — COBOL-to-Python migration pipeline.

Orchestrates all subsystems into a single end-to-end flow:

    Preprocessing → RAG Context → Agent Translation → Execution & Debug → Validation

Usage:
    python main.py                        # interactive CLI
    python main.py --file path/to/src.cob # from file

Programmatic:
    from main import run_pipeline
    result = run_pipeline(cobol_source)
"""

from __future__ import annotations

import logging
import os
import sys
import time
import textwrap
from typing import Any

# ── Module imports ────────────────────────────────────────────────────────
from config import PipelineConfig

# Preprocessing
from preprocessing.preprocessor import chunk_by_procedure, save_to_knowledge_base

# RAG
from rag.rag_engine import main as ingest_knowledge_base

# Agent system
from agents.agent_controller import AgentController

# Execution layer
from execution.executor import SandboxExecutor
from execution.validator import Validator
from execution.debug_loop import DebugLoop


# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger("pipeline")


# =====================================================================
#  Step functions — each stage is isolated for clarity and testability
# =====================================================================

def _step_preprocess(cobol_source: str, logs: list[str]) -> dict[str, Any]:
    """STEP 1 — Preprocess raw COBOL source into structured chunks.

    Returns a dict with the cleaned source and its procedural chunks,
    ready for the agent system to consume.
    """
    t0 = time.perf_counter()
    logs.append("[1/6] Preprocessing COBOL source …")
    logger.info("Preprocessing COBOL source (%d chars)", len(cobol_source))

    cleaned = cobol_source.strip()
    chunks = chunk_by_procedure(cleaned)

    elapsed = time.perf_counter() - t0
    logs.append(f"      ✓ Produced {len(chunks)} procedural chunk(s)  [{elapsed:.3f}s]")
    logger.info("Preprocessing complete: %d chunk(s) in %.3fs", len(chunks), elapsed)

    return {
        "cleaned_source": cleaned,
        "chunks": chunks,
        "chunk_count": len(chunks),
    }


def _step_retrieve_context(
    preprocessed: dict[str, Any],
    logs: list[str],
) -> dict[str, Any]:
    """STEP 2 — Build RAG context from the preprocessed chunks.

    In a full deployment this would query a vector store.  Here we build a
    lightweight context dict from the chunks themselves and any previously
    ingested knowledge-base artefacts on disk.
    """
    t0 = time.perf_counter()
    logs.append("[2/6] Retrieving RAG context …")
    logger.info("Building RAG context")

    chunks = preprocessed["chunks"]
    context: dict[str, Any] = {}

    # Attach chunk summaries as retrieval context for the agents
    for idx, chunk in enumerate(chunks):
        preview = chunk[:120].replace("\n", " ")
        context[f"chunk_{idx}"] = preview

    # Check if any knowledge-base documents exist on disk
    kb_dir = os.path.join("data", "knowledge_base")
    kb_files: list[str] = []
    if os.path.isdir(kb_dir):
        kb_files = [f for f in os.listdir(kb_dir) if f.endswith(".txt")]
        if kb_files:
            context["kb_documents"] = len(kb_files)
            # Attach first few KB snippets for extra context
            for kb_file in kb_files[:5]:
                path = os.path.join(kb_dir, kb_file)
                with open(path, "r", encoding="utf-8") as fh:
                    context[f"kb:{kb_file}"] = fh.read()[:200]

    elapsed = time.perf_counter() - t0
    logs.append(
        f"      ✓ Context keys: {len(context)}  |  "
        f"KB docs on disk: {len(kb_files)}  [{elapsed:.3f}s]"
    )
    logger.info("RAG context ready: %d keys in %.3fs", len(context), elapsed)
    return context


def _step_run_agents(
    cobol_source: str,
    context: dict[str, Any],
    config: PipelineConfig,
    logs: list[str],
) -> dict[str, Any]:
    """STEP 3 — Run the multi-agent translation pipeline.

    Delegates to `AgentController.run()` which internally handles:
        Router → StructureExpert → TranslationExpert → (DebugExpert) → TestExpert
    """
    t0 = time.perf_counter()
    logs.append("[3/6] Running agent pipeline (Route → Structure → Translate → Test) …")
    logger.info("Starting agent pipeline")

    controller = AgentController(config=config)
    agent_result = controller.run(cobol_source=cobol_source, context=context)

    complexity = agent_result["routing"]["complexity"]
    score = agent_result["routing"]["score"]
    code_len = len(agent_result["translation"].get("python_code", ""))
    test_count = len(agent_result["tests"].get("test_cases", []))
    iterations = agent_result["iterations"]

    elapsed = time.perf_counter() - t0
    logs.append(
        f"      ✓ Complexity : {complexity} (score {score})\n"
        f"      ✓ Translation: {code_len} chars\n"
        f"      ✓ Test cases : {test_count}\n"
        f"      ✓ Iterations : {iterations}  [{elapsed:.3f}s]"
    )
    logger.info(
        "Agent pipeline done: complexity=%s, code=%d chars, "
        "tests=%d, iters=%d  [%.3fs]",
        complexity, code_len, test_count, iterations, elapsed,
    )
    return agent_result


def _step_execute_and_debug(
    python_code: str,
    cobol_source: str,
    context: dict[str, Any],
    config: PipelineConfig,
    logs: list[str],
) -> dict[str, Any]:
    """STEP 4 — Sandbox-execute the generated code and run the self-debugging loop.

    Returns execution metadata including the (possibly improved) code,
    whether validation passed, and the number of debug iterations used.
    """
    t0 = time.perf_counter()
    logs.append("[4/6] Executing generated code in sandbox …")
    logger.info("Starting execution + debug loop")

    debug_loop = DebugLoop(max_retries=config.max_debug_retries)
    executor = SandboxExecutor(timeout_seconds=10)

    # Initial sandbox run to capture expected behaviour
    initial_exec = executor.execute(python_code)
    expected_output = initial_exec["stdout"].strip() if initial_exec["return_code"] == 0 else ""

    # Agent callback: when the debug loop detects a failure it asks the
    # agent system to produce a corrected version of the code.
    def _agent_fix_callback(fault_prompt: str) -> str:
        """Re-run the agent pipeline with the fault prompt as error context."""
        controller = AgentController(config=config)
        fix_result = controller.run(
            cobol_source=cobol_source,
            context=context,
            error_message=fault_prompt,
        )
        return fix_result["translation"].get("python_code", python_code)

    final_code, is_success = debug_loop.run_with_feedback(
        initial_code=python_code,
        expected_output=expected_output,
        mock_inputs=None,
        agent_callback=_agent_fix_callback,
    )

    elapsed = time.perf_counter() - t0
    status = "PASSED ✓" if is_success else "FAILED ✗"
    logs.append(f"      ✓ Debug loop status: {status}  [{elapsed:.3f}s]")
    logger.info("Debug loop finished: success=%s in %.3fs", is_success, elapsed)

    return {
        "final_code": final_code,
        "debug_passed": is_success,
        "initial_exec": initial_exec,
    }


def _step_validate(
    exec_info: dict[str, Any],
    logs: list[str],
) -> dict[str, Any]:
    """STEP 5 — Final validation gate on the executed code."""
    t0 = time.perf_counter()
    logs.append("[5/6] Running final validation gate …")
    logger.info("Running final validation")

    validator = Validator()
    executor = SandboxExecutor(timeout_seconds=10)

    final_exec = executor.execute(exec_info["final_code"])
    expected = exec_info["initial_exec"]["stdout"].strip()
    is_valid, report = validator.evaluate_execution(final_exec, expected)

    elapsed = time.perf_counter() - t0
    confidence = report.get("confidence_score", 0)
    reason = report.get("reason", "N/A")
    logs.append(
        f"      ✓ Valid: {is_valid}  |  Confidence: {confidence}%  |  "
        f"Reason: {reason}  [{elapsed:.3f}s]"
    )
    logger.info(
        "Validation: valid=%s  confidence=%.1f%%  reason=%s  [%.3fs]",
        is_valid, confidence, reason, elapsed,
    )
    return {
        "is_valid": is_valid,
        "confidence_score": confidence,
        "reason": reason,
        "report": report,
    }


# =====================================================================
#  Main pipeline
# =====================================================================

def run_pipeline(cobol_code: str) -> dict[str, Any]:
    """Execute the full COBOL-to-Python migration pipeline.

    Parameters
    ----------
    cobol_code : str
        Raw COBOL source code to migrate.

    Returns
    -------
    dict
        Structured output with keys:
            python_code      – final generated Python source
            logs             – list of human-readable log lines
            result           – summary dict (status, confidence, iterations …)
            agent_output     – full output from the agent subsystem
            validation       – validation report
            timing           – per-stage and total wall-clock times
    """
    pipeline_t0 = time.perf_counter()
    logs: list[str] = []
    timings: dict[str, float] = {}
    config = PipelineConfig()

    logs.append("=" * 64)
    logs.append("  COBOL → Python Migration Pipeline")
    logs.append("=" * 64)

    # ── Guard ─────────────────────────────────────────────────────────
    if not cobol_code or not cobol_code.strip():
        logs.append("[ERROR] Empty COBOL source provided. Aborting.")
        return {
            "python_code": "",
            "logs": logs,
            "result": {"status": "FAILED", "error": "Empty input"},
        }

    try:
        # ── Step 1: Preprocess ──────────────────────────────────────
        t = time.perf_counter()
        preprocessed = _step_preprocess(cobol_code, logs)
        timings["preprocess"] = time.perf_counter() - t

        # ── Step 2: RAG Context ─────────────────────────────────────
        t = time.perf_counter()
        context = _step_retrieve_context(preprocessed, logs)
        timings["rag_context"] = time.perf_counter() - t

        # ── Step 3: Agent Pipeline ──────────────────────────────────
        t = time.perf_counter()
        agent_output = _step_run_agents(
            cobol_source=preprocessed["cleaned_source"],
            context=context,
            config=config,
            logs=logs,
        )
        timings["agents"] = time.perf_counter() - t

        python_code = agent_output["translation"].get("python_code", "")

        if not python_code.strip():
            logs.append("[WARN] Agent produced empty Python code.")
            return {
                "python_code": "",
                "logs": logs,
                "result": {"status": "FAILED", "error": "No code generated"},
                "agent_output": agent_output,
            }

        # ── Step 4: Execute + Debug Loop ────────────────────────────
        t = time.perf_counter()
        exec_info = _step_execute_and_debug(
            python_code=python_code,
            cobol_source=preprocessed["cleaned_source"],
            context=context,
            config=config,
            logs=logs,
        )
        timings["execution"] = time.perf_counter() - t

        # ── Step 5: Validate ────────────────────────────────────────
        t = time.perf_counter()
        validation = _step_validate(exec_info, logs)
        timings["validation"] = time.perf_counter() - t

        # ── Step 6: Assemble result ─────────────────────────────────
        total_time = time.perf_counter() - pipeline_t0
        timings["total"] = total_time

        status = "SUCCESS" if validation["is_valid"] else "PARTIAL"
        logs.append(f"[6/6] Pipeline complete — {status}  [{total_time:.3f}s total]")
        logs.append("=" * 64)

        return {
            "python_code": exec_info["final_code"],
            "logs": logs,
            "result": {
                "status": status,
                "confidence_score": validation["confidence_score"],
                "debug_passed": exec_info["debug_passed"],
                "iterations": agent_output["iterations"],
                "complexity": agent_output["routing"]["complexity"],
            },
            "agent_output": agent_output,
            "validation": validation,
            "timing": timings,
        }

    except Exception as exc:
        total_time = time.perf_counter() - pipeline_t0
        timings["total"] = total_time
        logs.append(f"[ERROR] Pipeline failed: {type(exc).__name__}: {exc}")
        logs.append("=" * 64)
        logger.exception("Pipeline error")
        return {
            "python_code": "",
            "logs": logs,
            "result": {
                "status": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            },
            "timing": timings,
        }


# =====================================================================
#  CLI entry point
# =====================================================================

SAMPLE_COBOL = textwrap.dedent("""\
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
          88 IS-ACTIVE   VALUE 'Y'.
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
""")


def _print_banner() -> None:
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║     COBOL → Python  Migration Pipeline  (CLI)              ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  Options:                                                  ║")
    print("║    1  Paste COBOL source interactively                     ║")
    print("║    2  Load from file                                       ║")
    print("║    3  Run with built-in sample (PAYROLL)                   ║")
    print("║    q  Quit                                                 ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()


def _read_from_terminal() -> str:
    """Read multi-line COBOL source from stdin until a blank line."""
    print("Paste your COBOL source below.  Enter a blank line to finish:\n")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)


def _read_from_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main() -> None:
    """Interactive CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-5s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # Quick path: --file flag
    if len(sys.argv) > 2 and sys.argv[1] == "--file":
        filepath = sys.argv[2]
        if not os.path.isfile(filepath):
            print(f"Error: file not found — {filepath}")
            sys.exit(1)
        source = _read_from_file(filepath)
        result = run_pipeline(source)
        _display_result(result)
        return

    _print_banner()

    choice = input("Select option [1/2/3/q]: ").strip().lower()

    if choice == "q":
        print("Goodbye.")
        return
    elif choice == "1":
        source = _read_from_terminal()
    elif choice == "2":
        path = input("Enter file path: ").strip()
        if not os.path.isfile(path):
            print(f"Error: file not found — {path}")
            sys.exit(1)
        source = _read_from_file(path)
    elif choice == "3":
        source = SAMPLE_COBOL
        print("Using built-in PAYROLL sample.\n")
    else:
        print(f"Unknown option: {choice}")
        return

    result = run_pipeline(source)
    _display_result(result)


def _display_result(result: dict[str, Any]) -> None:
    """Pretty-print the pipeline result to the terminal."""
    print()
    # Logs
    for line in result.get("logs", []):
        print(line)

    # Summary
    res = result.get("result", {})
    print()
    print("┌─────────────── Summary ───────────────┐")
    print(f"│  Status      : {res.get('status', 'N/A'):<23}│")
    if "confidence_score" in res:
        print(f"│  Confidence  : {res['confidence_score']:<23}│")
    if "complexity" in res:
        print(f"│  Complexity  : {res['complexity']:<23}│")
    if "iterations" in res:
        print(f"│  Iterations  : {res['iterations']:<23}│")
    if "error" in res:
        print(f"│  Error       : {res['error']:<23}│")
    print("└───────────────────────────────────────┘")

    # Timing
    timing = result.get("timing", {})
    if timing:
        print()
        print("  Timing breakdown:")
        for stage, secs in timing.items():
            bar = "█" * int(min(secs * 20, 40))
            print(f"    {stage:<14} {secs:>7.3f}s  {bar}")

    # Generated code preview
    code = result.get("python_code", "")
    if code:
        print()
        print("─── Generated Python (first 40 lines) " + "─" * 26)
        for i, line in enumerate(code.splitlines()[:40], 1):
            print(f"  {i:3d} │ {line}")
        if code.count("\n") > 40:
            print(f"  ... ({code.count(chr(10)) + 1} lines total)")
    print()


# =====================================================================
if __name__ == "__main__":
    main()
