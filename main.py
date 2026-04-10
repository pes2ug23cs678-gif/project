"""Main integration layer — COBOL-to-Python migration pipeline.

Model combination:
    Translation Expert  ->  DeepSeek V3 via OpenAI-compatible API
    Debug Expert        ->  DeepSeek V3 via OpenAI-compatible API
    Router (SLM)        ->  SmolLM via Ollama (local, lightweight)
    Execution           ->  subprocess sandbox (no model at all)

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

# Load .env before anything else
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — rely on shell env vars

# ── Module imports ────────────────────────────────────────────────────────
from config import SANDBOX_TIMEOUT, SANDBOX_MAX_ITER

# Preprocessing
from preprocessing.preprocessor import chunk_by_procedure

# Agent system (new model stack)
from agents.router import classify
from agents.translation_expert import generate_python

# Execution layer (new: sandbox.py + debug_loop.py)
from execution.sandbox import sandbox_execute
from execution.debug_loop import run_debug_loop


# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger("pipeline")


# =====================================================================
#  Step functions
# =====================================================================

def _step_preprocess(cobol_source: str, logs: list[str]) -> dict[str, Any]:
    """STEP 1 — Preprocess raw COBOL source into structured chunks."""
    t0 = time.perf_counter()
    logs.append("[1/7] Preprocessing COBOL source …")
    logger.info("Preprocessing COBOL source (%d chars)", len(cobol_source))

    cleaned = cobol_source.strip()
    chunks = chunk_by_procedure(cleaned)

    elapsed = time.perf_counter() - t0
    logs.append(f"      [OK] Produced {len(chunks)} procedural chunk(s)  [{elapsed:.3f}s]")
    logger.info("Preprocessing complete: %d chunk(s) in %.3fs", len(chunks), elapsed)

    return {
        "cleaned_source": cleaned,
        "chunks": chunks,
        "chunk_count": len(chunks),
    }


def _step_build_analysis(preprocessed: dict[str, Any], logs: list[str]) -> dict[str, Any]:
    """STEP 2 — Build a lightweight structured analysis from preprocessed chunks."""
    t0 = time.perf_counter()
    logs.append("[2/7] Building structured analysis …")

    cleaned = preprocessed["cleaned_source"]
    code_upper = cleaned.upper()

    # Extract program ID
    program_id = "UNKNOWN"
    for line in cleaned.splitlines():
        if "PROGRAM-ID" in line.upper():
            parts = line.split(".")
            if parts:
                program_id = parts[0].split()[-1].strip()
            break

    # Extract paragraph names (lines ending in a period with no leading space or known keywords)
    paragraphs = []
    skip_keywords = {
        "IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE",
        "WORKING-STORAGE", "FILE-CONTROL", "INPUT-OUTPUT",
        "LINKAGE", "CONFIGURATION", "FILE",
    }
    for line in cleaned.splitlines():
        stripped = line.strip()
        if (
            stripped.endswith(".")
            and not stripped.startswith("*")
            and " " not in stripped[:-1]
            and stripped[:-1].upper() not in skip_keywords
            and len(stripped) < 40
        ):
            paragraphs.append(stripped[:-1])

    analysis = {
        "program_id": program_id,
        "paragraphs": paragraphs,
        "has_file_io": "FILE-CONTROL" in code_upper or "SELECT" in code_upper,
        "has_occurs": "OCCURS" in code_upper,
        "has_redefines": "REDEFINES" in code_upper,
        "line_count": len([l for l in cleaned.splitlines() if l.strip()]),
    }

    elapsed = time.perf_counter() - t0
    logs.append(
        f"      [OK] Program: {program_id}  |  Paragraphs: {len(paragraphs)}  "
        f"|  File I/O: {analysis['has_file_io']}  [{elapsed:.3f}s]"
    )
    return analysis


def _step_rag_context(preprocessed: dict[str, Any], logs: list[str]) -> dict[str, Any]:
    """STEP 3 — Lightweight RAG context from chunks + on-disk knowledge base."""
    t0 = time.perf_counter()
    logs.append("[3/7] Building RAG context …")

    chunks = preprocessed["chunks"]
    context: dict[str, Any] = {}

    for idx, chunk in enumerate(chunks):
        preview = chunk[:120].replace("\n", " ")
        context[f"chunk_{idx}"] = preview

    kb_dir = os.path.join("data", "knowledge_base")
    kb_files: list[str] = []
    if os.path.isdir(kb_dir):
        kb_files = [f for f in os.listdir(kb_dir) if f.endswith(".txt")]
        if kb_files:
            context["kb_documents"] = len(kb_files)
            for kb_file in kb_files[:5]:
                path = os.path.join(kb_dir, kb_file)
                with open(path, "r", encoding="utf-8") as fh:
                    context[f"kb:{kb_file}"] = fh.read()[:200]

    elapsed = time.perf_counter() - t0
    logs.append(
        f"      [OK] Context keys: {len(context)}  |  "
        f"KB docs on disk: {len(kb_files)}  [{elapsed:.3f}s]"
    )
    logger.info("RAG context ready: %d keys in %.3fs", len(context), elapsed)
    return context


def _step_route(
    cobol_source: str,
    analysis: dict[str, Any],
    logs: list[str],
) -> str:
    """STEP 4 — Route via SmolLM (Expert 2) to classify as simple or complex."""
    t0 = time.perf_counter()
    logs.append("[4/7] Routing task (Expert 2) …")
    logger.info("Routing via SmolLM")

    route = classify(cobol_source, analysis)

    elapsed = time.perf_counter() - t0
    logs.append(f"      [OK] Route: {route}  (SmolLM or rule-based fallback)  [{elapsed:.3f}s]")
    logger.info("Route: %s in %.3fs", route, elapsed)
    return route


def _step_translate(
    cobol_source: str,
    analysis: dict[str, Any],
    logs: list[str],
) -> str:
    """STEP 5 — Translate COBOL → Python via DeepSeek V3 (Expert 3)."""
    t0 = time.perf_counter()
    logs.append("[5/7] Generating Python code (Expert 3) …")
    logger.info("Translating via DeepSeek V3")

    python_code = generate_python(cobol_source, structured_analysis=analysis)

    char_count = len(python_code)
    line_count = python_code.count("\n") + 1
    elapsed = time.perf_counter() - t0
    logs.append(
        f"      [OK] DeepSeek V3 — {char_count} chars, {line_count} lines  [{elapsed:.3f}s]"
    )
    logger.info("Translation: %d chars, %d lines in %.3fs", char_count, line_count, elapsed)
    return python_code


def _step_sandbox_debug(
    python_code: str,
    logs: list[str],
) -> dict[str, Any]:
    """STEP 6 — Sandbox execution + debug loop (Expert 4 for hard errors)."""
    t0 = time.perf_counter()
    logs.append("[6/7] Sandbox execution + debug loop …")
    logger.info("Running sandbox + debug loop (max %d iterations)", SANDBOX_MAX_ITER)

    debug_result = run_debug_loop(
        initial_code=python_code,
        max_iterations=SANDBOX_MAX_ITER,
    )

    elapsed = time.perf_counter() - t0
    status = "PASSED [OK]" if debug_result.success else "FAILED [FAIL]"
    logs.append(
        f"      [OK] {status}  |  Iterations: {debug_result.iterations_used}  [{elapsed:.3f}s]"
    )
    if not debug_result.success and debug_result.error_summary:
        logs.append(f"      [FAIL] {debug_result.error_summary}")
    logger.info(
        "Debug loop: success=%s  iterations=%d  in %.3fs",
        debug_result.success, debug_result.iterations_used, elapsed,
    )
    return {
        "final_code":    debug_result.final_code,
        "debug_passed":  debug_result.success,
        "iterations":    debug_result.iterations_used,
        "debug_log":     debug_result.log,
        "error_summary": debug_result.error_summary,
        "_debug_result": debug_result,   # raw object for confidence scoring
    }


def _step_validate(
    exec_info: dict[str, Any],
    logs: list[str],
) -> dict[str, Any]:
    """STEP 7 — Final validation gate."""
    t0 = time.perf_counter()
    logs.append("[7/7] Validation …")
    logger.info("Running final validation")

    final_code = exec_info["final_code"]
    result = sandbox_execute(final_code, timeout=SANDBOX_TIMEOUT)

    passed = result["returncode"] == 0 and not result["stderr"].strip()
    pass_rate = 100 if passed else 0

    elapsed = time.perf_counter() - t0
    logs.append(f"      [OK] Pass rate: {pass_rate}%  [{elapsed:.3f}s]")
    if not passed and result["stderr"].strip():
        logs.append(f"      [FAIL] {result['stderr'].strip().splitlines()[-1]}")
    logger.info("Validation: pass_rate=%d%%  in %.3fs", pass_rate, elapsed)

    return {
        "is_valid":   passed,
        "pass_rate":  pass_rate,
        "stdout":     result["stdout"],
        "stderr":     result["stderr"],
        "returncode": result["returncode"],
    }


# =====================================================================
#  Confidence scorer
# =====================================================================

def compute_confidence(debug_result, validation_report: dict) -> float:
    """Score 0–100 based on pass rate and how few iterations were needed."""
    if not debug_result.success:
        return 0.0
    pass_rate   = validation_report.get("pass_rate", 0) / 100.0  # normalise to 0-1
    iterations  = debug_result.iterations_used
    max_iter    = SANDBOX_MAX_ITER
    # High pass rate + fewer iterations = higher confidence
    iter_score  = 1.0 - ((iterations - 1) / max_iter)
    confidence  = (pass_rate * 0.7) + (iter_score * 0.3)
    return round(min(max(confidence, 0.0), 1.0) * 100, 1)


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
            python_code  – final generated Python source
            logs         – list of human-readable log lines
            result       – summary dict (status, pass_rate, iterations …)
            validation   – validation report
            timing       – per-stage and total wall-clock times
    """
    pipeline_t0 = time.perf_counter()
    logs: list[str] = []
    timings: dict[str, float] = {}

    logs.append("=" * 64)
    logs.append("  COBOL -> Python Migration Pipeline")
    logs.append("  Stack: DeepSeek V3 (translate+debug) | SmolLM (route) | subprocess (exec)")
    logs.append("=" * 64)

    if not cobol_code or not cobol_code.strip():
        logs.append("[ERROR] Empty COBOL source provided. Aborting.")
        return {
            "python_code": "",
            "logs": logs,
            "result": {"status": "FAILED", "error": "Empty input"},
        }

    try:
        # ── Step 1: Preprocess ──────────────────────────────────────
        t = time.time()
        preprocessed = _step_preprocess(cobol_code, logs)
        timings["preprocess"] = round(time.time() - t, 3)

        # ── Step 2: Structured analysis ────────────────────────────
        t = time.time()
        analysis = _step_build_analysis(preprocessed, logs)
        timings["structure"] = round(time.time() - t, 3)

        # ── Step 3: RAG context ────────────────────────────────────
        t = time.time()
        _step_rag_context(preprocessed, logs)
        timings["rag"] = round(time.time() - t, 3)

        # ── Step 4: Route (SmolLM) ─────────────────────────────────
        t = time.time()
        route = _step_route(preprocessed["cleaned_source"], analysis, logs)
        timings["router"] = round(time.time() - t, 3)

        # ── Step 5: Translate (Groq) ───────────────────────────────
        t = time.time()
        python_code = _step_translate(
            preprocessed["cleaned_source"], analysis, logs
        )
        timings["translation"] = round(time.time() - t, 3)

        if not python_code.strip():
            logs.append("[WARN] LLM produced empty Python code.")
            return {
                "python_code": "",
                "logs": logs,
                "result": {"status": "FAILED", "error": "No code generated"},
            }

        # ── Step 6: Sandbox + debug loop ──────────────────────────
        t = time.time()
        exec_info = _step_sandbox_debug(python_code, logs)
        timings["execution"] = round(time.time() - t, 3)

        # ── Step 7: Validate ───────────────────────────────────────
        t = time.time()
        validation = _step_validate(exec_info, logs)
        timings["validation"] = round(time.time() - t, 3)

        # ── Assemble result ────────────────────────────────────────
        total_time = round(sum(v for k, v in timings.items()), 3)
        timings["total"] = total_time

        status = "SUCCESS" if validation["is_valid"] else "PARTIAL"
        logs.append(f"Pipeline complete — {status}  [{total_time:.3f}s total]")
        logs.append("=" * 64)

        final_code    = exec_info["final_code"]
        debug_log     = exec_info["debug_log"]
        pass_rate_pct = validation["pass_rate"]   # 0 or 100
        confidence    = compute_confidence(
            exec_info["_debug_result"],
            {"pass_rate": pass_rate_pct},
        )

        return {
            "python_code": final_code,
            "logs": logs,
            "result": {
                "status":           status,
                "pass_rate":        pass_rate_pct,
                "debug_passed":     exec_info["debug_passed"],
                "iterations":       exec_info["iterations"],
                "complexity":       route,
                "confidence_score": confidence,
            },
            "confidence":  confidence,  # top-level alias for UI
            "validation":  validation,
            "timing":      timings,
            # ── Per-agent metadata — read by the Agents tab ─────────
            "agents": {
                "expert_1_structure": {
                    "name":       "Structure Analyst",
                    "model":      "rule-based (no LLM)",
                    "program_id": analysis.get("program_id", "UNKNOWN"),
                    "complexity": "complex" if any([
                        analysis.get("has_file_io"),
                        analysis.get("has_occurs"),
                        analysis.get("has_redefines"),
                        analysis.get("line_count", 0) > 40,
                    ]) else "simple",
                    "paragraphs": analysis.get("paragraphs", []),
                    "variables":  {},
                    "file_io":    analysis.get("has_file_io", False),
                    "status":     "success",
                },
                "expert_2_router": {
                    "name":    "SLM Router",
                    "model":   "SmolLM via Ollama (rule-based fallback)",
                    "decision": route,
                    "reason":  "complex signals detected" if route == "complex"
                               else "no complex signals",
                    "status":  "success",
                },
                "expert_3_translation": {
                    "name":   "Translation Engine",
                    "model":  "Groq llama-3.3-70b-versatile",
                    "chars":  len(final_code),
                    "lines":  len(final_code.splitlines()),
                    "status": "success",
                },
                "expert_4_debug": {
                    "name":       "Debug Expert",
                    "model":      "Groq llama-3.3-70b-versatile (escalation) + rule-based (quick fixes)",
                    "iterations": exec_info["iterations"],
                    "log": [
                        {
                            "iteration":   r.iteration,
                            "error_type":  r.error_type,
                            "fix_applied": r.fix_applied,
                            "status":      r.status,
                        }
                        for r in debug_log
                    ],
                    "status": "success" if exec_info["debug_passed"] else "failed",
                },
                "expert_5_validation": {
                    "name":      "Validator",
                    "model":     "rule-based (no LLM)",
                    "pass_rate": 1.0 if pass_rate_pct == 100 else 0.0,
                    "total":     1,
                    "passed":    1 if pass_rate_pct == 100 else 0,
                    "status":    "success" if pass_rate_pct == 100 else "failed",
                },
            },
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
       PROGRAM-ID. ENTERPRISE-LEDGER-SYSTEM.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCOUNT-FILE    ASSIGN TO 'accounts.dat'.
           SELECT TRANSACTION-FILE ASSIGN TO 'transactions.dat'.
           SELECT REPORT-FILE     ASSIGN TO 'report.txt'.
       DATA DIVISION.
       FILE SECTION.
       FD ACCOUNT-FILE.
       01 ACCOUNT-RECORD.
          05 ACC-ID        PIC 9(6).
          05 ACC-NAME      PIC X(25).
          05 ACC-TYPE      PIC X(1).
          05 ACC-BALANCE   PIC S9(9)V99 COMP-3.
          05 ACC-STATUS    PIC X(1).
       FD TRANSACTION-FILE.
       01 TRANSACTION-RECORD.
          05 TRANS-ACC-ID  PIC 9(6).
          05 TRANS-TYPE    PIC X(1).
          05 TRANS-AMOUNT  PIC S9(7)V99 COMP-3.
          05 TRANS-DATE    PIC 9(8).
       FD REPORT-FILE.
       01 REPORT-REC      PIC X(120).
       WORKING-STORAGE SECTION.
       01 WS-EOF-ACC     PIC X VALUE 'N'.
       01 WS-EOF-TRANS   PIC X VALUE 'N'.
       01 WS-TOT-DEPOSIT  PIC S9(9)V99 COMP-3 VALUE ZERO.
       01 WS-TOT-WITHDRAW PIC S9(9)V99 COMP-3 VALUE ZERO.
       01 WS-TOT-ERRORS   PIC 9(5)      VALUE ZERO.
       PROCEDURE DIVISION.
       MAIN-LOGIC.
           PERFORM INIT-FILES.
           PERFORM PROCESS-ACCOUNTS UNTIL WS-EOF-ACC = 'Y'.
           PERFORM GENERATE-REPORT.
           PERFORM CLEANUP.
           STOP RUN.
       INIT-FILES.
           OPEN INPUT  ACCOUNT-FILE
                INPUT  TRANSACTION-FILE
                OUTPUT REPORT-FILE.
           PERFORM READ-ACCOUNT.
       READ-ACCOUNT.
           READ ACCOUNT-FILE AT END MOVE 'Y' TO WS-EOF-ACC.
       PROCESS-ACCOUNTS.
           PERFORM APPLY-TRANSACTIONS.
           PERFORM READ-ACCOUNT.
       APPLY-TRANSACTIONS.
           MOVE 'N' TO WS-EOF-TRANS.
           PERFORM READ-TRANSACTION.
           PERFORM UPDATE-BALANCE UNTIL WS-EOF-TRANS = 'Y'.
       READ-TRANSACTION.
           READ TRANSACTION-FILE AT END MOVE 'Y' TO WS-EOF-TRANS.
       UPDATE-BALANCE.
           EVALUATE TRANS-TYPE
               WHEN 'D'
                   ADD TRANS-AMOUNT TO ACC-BALANCE
                   ADD TRANS-AMOUNT TO WS-TOT-DEPOSIT
               WHEN 'W'
                   SUBTRACT TRANS-AMOUNT FROM ACC-BALANCE
                   ADD TRANS-AMOUNT TO WS-TOT-WITHDRAW
               WHEN OTHER
                   ADD 1 TO WS-TOT-ERRORS
           END-EVALUATE.
           PERFORM READ-TRANSACTION.
       GENERATE-REPORT.
           MOVE 'LEDGER SUMMARY' TO REPORT-REC.
           WRITE REPORT-REC.
       CLEANUP.
           CLOSE ACCOUNT-FILE TRANSACTION-FILE REPORT-FILE.
""")


def _print_banner() -> None:
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║     COBOL -> Python  Migration Pipeline  (CLI)             ║")
    print("║  Stack:  DeepSeek V3 | SmolLM | subprocess sandbox        ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  Options:                                                  ║")
    print("║    1  Paste COBOL source interactively                     ║")
    print("║    2  Load from file                                       ║")
    print("║    3  Run with built-in sample (ENTERPRISE-LEDGER-SYSTEM)  ║")
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
        print("Using built-in ENTERPRISE-LEDGER-SYSTEM sample.\n")
    else:
        print(f"Unknown option: {choice}")
        return

    result = run_pipeline(source)
    _display_result(result)


def _display_result(result: dict[str, Any]) -> None:
    """Pretty-print the pipeline result to the terminal."""
    print()
    for line in result.get("logs", []):
        print(line)

    res = result.get("result", {})
    print()
    print("┌─────────────── Summary ───────────────┐")
    print(f"│  Status      : {res.get('status', 'N/A'):<23}│")
    if "pass_rate" in res:
        print(f"│  Pass rate   : {str(res['pass_rate']) + '%':<23}│")
    if "complexity" in res:
        print(f"│  Complexity  : {res['complexity']:<23}│")
    if "iterations" in res:
        print(f"│  Iterations  : {res['iterations']:<23}│")
    if "error" in res:
        print(f"│  Error       : {str(res['error'])[:23]:<23}│")
    print("└───────────────────────────────────────┘")

    timing = result.get("timing", {})
    if timing:
        print()
        print("  Timing breakdown:")
        for stage, secs in timing.items():
            bar = "█" * int(min(secs * 20, 40))
            print(f"    {stage:<14} {secs:>7.3f}s  {bar}")

    code = result.get("python_code", "")
    if code:
        print()
        print("--- Generated Python (first 40 lines) " + "-" * 26)
        for i, line in enumerate(code.splitlines()[:40], 1):
            print(f"  {i:3d} │ {line}")
        if code.count("\n") > 40:
            print(f"  ... ({code.count(chr(10)) + 1} lines total)")
    print()


# =====================================================================
if __name__ == "__main__":
    main()
