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
from config import SANDBOX_TIMEOUT, SANDBOX_MAX_ITER, PYTEST_SANDBOX_TIMEOUT

# Preprocessing
from preprocessing.preprocessor import chunk_by_procedure

# Agent system (new model stack)
from agents.router import classify
from agents.translation_expert import generate_python
from agents.test_expert import TestExpert

# Execution layer (new: sandbox.py + debug_loop.py)
from execution.sandbox import sandbox_execute, sandbox_pytest
from execution.debug_loop import run_debug_loop

# Explainability
from explainability import generate_xai_report

# Shared TestExpert instance
_test_expert = TestExpert()


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
            # Handle both "PROGRAM-ID. NAME." and "PROGRAM-ID NAME."
            after_keyword = line.upper().split("PROGRAM-ID")[-1]
            # Strip dots, spaces, and other delimiters
            name = after_keyword.replace(".", " ").strip().split()[0] if after_keyword.replace(".", " ").strip() else "UNKNOWN"
            # Find original case from the line
            for token in line.split():
                if token.strip(".").upper() == name.upper():
                    program_id = token.strip(".")
                    break
            else:
                program_id = name
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


def _step_rag_context(
    preprocessed: dict[str, Any],
    logs: list[str],
    route: str | None = None,
) -> dict[str, Any]:
    """STEP 3 — Semantic RAG context with keyword-based fallback and distractor filtering."""
    t0 = time.perf_counter()
    logs.append("[3/7] Building RAG context …")

    context: dict[str, Any] = {}

    # 1. Chunk previews (keep existing behavior for chunk contexts)
    chunks = preprocessed.get("chunks", [])
    for idx, chunk in enumerate(chunks):
        preview = chunk[:120].replace("\n", " ")
        context[f"chunk_{idx}"] = preview

    # 2. ExpertRAG Gating: Skip KB retrieval for simple routes
    if route == "simple":
        elapsed = time.perf_counter() - t0
        logs.append(f"      [RAG] Skipped — simple route (ExpertRAG gating) [{elapsed:.3f}s]")
        logger.info("RAG retrieval skipped for simple route")
        return context

    # 3. Retrieve relevant documents using semantic search (ChromaDB)
    cleaned_source = preprocessed.get("cleaned_source", "")
    retrieved_docs = []

    # Try semantic retrieval (Phase 2)
    try:
        from rag.vector_store import retrieve
        # Use first 2000 characters as search query
        retrieved_docs = retrieve(cleaned_source[:2000], top_k=5)
    except Exception as exc:
        logger.warning("ChromaDB retrieval failed, falling back to keyword-based retrieval: %s", exc)
        # Keyword-based fallback (Phase 1)
        kb_dir = os.path.join("data", "knowledge_base")
        if os.path.isdir(kb_dir):
            code_upper = cleaned_source.upper()
            RELEVANCE_MAP = {
                "cobol_evaluate_pattern.txt": ["EVALUATE", "WHEN"],
                "cobol_fileio_pattern.txt":   ["FILE-CONTROL", "SELECT", "READ", "WRITE", "OPEN"],
                "cobol_occurs_pattern.txt":   ["OCCURS", "VARYING"],
            }
            for kb_file in os.listdir(kb_dir):
                if kb_file in RELEVANCE_MAP:
                    keywords = RELEVANCE_MAP[kb_file]
                    if any(kw in code_upper for kw in keywords):
                        path = os.path.join(kb_dir, kb_file)
                        try:
                            with open(path, "r", encoding="utf-8") as fh:
                                content = fh.read()
                            retrieved_docs.append({
                                "content": content,
                                "source": kb_file,
                                "type": "pattern",
                                "relevance_score": 1.0
                            })
                        except Exception as read_err:
                            logger.error("Failed to read fallback KB file %s: %s", path, read_err)

    # 4. Filter distractors & inject full pattern files (OPEN-RAG Distractor concept)
    injected_count = 0
    code_upper = cleaned_source.upper()

    for doc in retrieved_docs:
        source = doc["source"]
        doc_type = doc.get("type", "unknown")

        # Determine if doc is a distractor
        is_distractor = False
        if doc_type == "reference":
            # Raw COBOL references are distractors unless we are translating a program of the same name
            is_distractor = True
        elif source == "cobol_evaluate_pattern.txt" and "EVALUATE" not in code_upper:
            is_distractor = True
        elif source == "cobol_fileio_pattern.txt" and not any(k in code_upper for k in ["FILE-CONTROL", "SELECT", "OPEN", "READ", "WRITE"]):
            is_distractor = True
        elif source == "cobol_occurs_pattern.txt" and "OCCURS" not in code_upper:
            is_distractor = True

        if not is_distractor:
            # Inject full content (no truncation)
            context[f"kb:{source}"] = doc["content"]
            injected_count += 1
            logger.info("Injected relevant KB document: %s", source)

    elapsed = time.perf_counter() - t0
    logs.append(
        f"      [OK] Injected {injected_count} relevant pattern(s)  [{elapsed:.3f}s]"
    )
    logger.info("RAG context ready with %d injected documents in %.3fs", injected_count, elapsed)
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
    rag_context: dict[str, Any] = None,
) -> str:
    """STEP 5 — Translate COBOL → Python via DeepSeek V3 (Expert 3).

    Parameters
    ----------
    rag_context:
        Context dict from ``_step_rag_context()``.  Forwarded to
        ``generate_python()`` so KB snippets are injected into the LLM prompt.
    """
    t0 = time.perf_counter()
    logs.append("[5/7] Generating Python code (Expert 3) …")
    logger.info("Translating via DeepSeek V3")

    kb_count = sum(1 for k in (rag_context or {}) if k.startswith("kb:"))
    if kb_count:
        logs.append(f"      [RAG] Injecting {kb_count} KB document(s) into translation prompt")

    python_code = generate_python(
        cobol_source,
        structured_analysis=analysis,
        rag_context=rag_context,
    )

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
    test_cases: list = None,
    test_code: str = "",
    module_name: str = "migrated",
) -> dict[str, Any]:
    """STEP 6 — Sandbox execution + debug loop (Expert 4 for hard errors).

    Parameters
    ----------
    test_cases:
        Oracle list from the COBOL scenario step.  Forwarded to
        ``run_debug_loop()`` so logic errors (assertion failures, not
        crashes) can be diagnosed and repaired by the LLM.
    test_code:
        The generated pytest suite (from Step 5.5).  Forwarded to
        ``run_debug_loop()`` so that crash-free but logically wrong code
        can be caught and corrected by running the full test suite inside
        each debug iteration.
    module_name:
        Name used when writing the translated module inside the sandbox
        (must match the ``from <module_name> import *`` in test_code).
    """
    t0 = time.perf_counter()
    logs.append("[6/7] Sandbox execution + debug loop …")
    logger.info("Running sandbox + debug loop (max %d iterations)", SANDBOX_MAX_ITER)

    if test_cases:
        logs.append(f"      [DEBUG] Supplying {len(test_cases)} test oracle(s) for logic correction")
    if test_code.strip():
        logs.append(f"      [DEBUG] pytest suite wired into debug loop (module={module_name!r}) — logic failures will trigger re-fix")

    debug_result = run_debug_loop(
        initial_code=python_code,
        test_cases=test_cases or [],
        max_iterations=SANDBOX_MAX_ITER,
        test_code=test_code,
        module_name=module_name,
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


def _step_generate_cobol_scenarios(
    cobol_source: str,
    analysis: dict[str, Any],
    logs: list[str],
) -> dict[str, Any]:
    """STEP 1.5 — Derive abstract COBOL test scenarios (fast, rule-based)."""
    t0 = time.perf_counter()
    logs.append("[1.5] Generating COBOL test scenarios …")
    logger.info("Generating COBOL test scenarios")

    # Use TestExpert in rule-based mode (no python_code yet, no LLM call)
    result = _test_expert.run(
        python_code="",
        cobol_source=cobol_source,
        structure_analysis=analysis,
    )

    scenario_count = len(result.get("test_cases", []))
    elapsed = time.perf_counter() - t0
    logs.append(f"      [OK] {scenario_count} test scenario(s) derived  [{elapsed:.3f}s]")
    logger.info("COBOL scenarios: %d in %.3fs", scenario_count, elapsed)
    return result


def _step_generate_pytest(
    python_code: str,
    cobol_source: str,
    analysis: dict[str, Any],
    logs: list[str],
) -> dict[str, Any]:
    """STEP 5.5 — Generate filled pytest suite via LLM (TestExpert)."""
    t0 = time.perf_counter()
    logs.append("[5.5] Generating equivalent pytest suite (LLM) …")
    logger.info("Generating pytest suite via LLM")

    result = _test_expert.run(
        python_code=python_code,
        cobol_source=cobol_source,
        structure_analysis=analysis,
    )

    elapsed = time.perf_counter() - t0
    logs.append(f"      [OK] Pytest suite generated  [{elapsed:.3f}s]")
    logger.info("Pytest suite ready in %.3fs", elapsed)
    return result


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

    # Filter Python warnings from stderr (DeprecationWarning, etc.)
    import re as _re
    real_stderr = "\n".join(
        line for line in result["stderr"].splitlines()
        if not _re.match(r'^.*:\d+:\s+\w*Warning:', line)
        and not line.strip().startswith("warnings.warn(")
    )

    passed = result["returncode"] == 0 and not real_stderr.strip()
    pass_rate = 100 if passed else 0

    elapsed = time.perf_counter() - t0
    logs.append(f"      [OK] Pass rate: {pass_rate}%  [{elapsed:.3f}s]")
    if not passed and real_stderr.strip():
        logs.append(f"      [FAIL] {real_stderr.strip().splitlines()[-1]}")
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

        # ── Step 1.5: COBOL test scenarios (rule-based) ────────────
        t = time.time()
        cobol_scenarios = _step_generate_cobol_scenarios(
            preprocessed["cleaned_source"], analysis, logs
        )
        timings["cobol_scenarios"] = round(time.time() - t, 3)

        # ── Step 4: Route (SmolLM) ─────────────────────────────────
        t = time.time()
        route = _step_route(preprocessed["cleaned_source"], analysis, logs)
        timings["router"] = round(time.time() - t, 3)

        # ── Step 3: RAG context ────────────────────────────────────
        t = time.time()
        rag_context = _step_rag_context(preprocessed, logs, route=route)
        timings["rag"] = round(time.time() - t, 3)

        # ── Step 5: Translate (Groq) ───────────────────────────────
        t = time.time()
        python_code = _step_translate(
            preprocessed["cleaned_source"], analysis, logs,
            rag_context=rag_context,  # FIX: forward RAG context to translation agent
        )
        timings["translation"] = round(time.time() - t, 3)

        if not python_code.strip():
            logs.append("[WARN] LLM produced empty Python code.")
            return {
                "python_code": "",
                "logs": logs,
                "result": {"status": "FAILED", "error": "No code generated"},
            }

        # ── Step 5.5: Generate filled pytest suite (LLM) ──────────
        t = time.time()
        pytest_data = _step_generate_pytest(
            python_code, preprocessed["cleaned_source"], analysis, logs
        )
        timings["pytest_gen"] = round(time.time() - t, 3)

        # ── Derive module name from COBOL program ID (shared by Step 6 & 7.5) ──
        module_name = analysis.get("program_id", "program").lower().replace("-", "_")

        # ── Step 6: Sandbox + debug loop ──────────────────────────
        t = time.time()
        exec_info = _step_sandbox_debug(
            python_code, logs,
            test_cases=cobol_scenarios.get("test_cases", []),
            test_code=pytest_data.get("test_code", ""),
            module_name=module_name,   # FIX: pass correct name so sandbox_pytest imports work
        )
        timings["execution"] = round(time.time() - t, 3)

        # ── Step 7: Validate ───────────────────────────────────────
        t = time.time()
        validation = _step_validate(exec_info, logs)
        timings["validation"] = round(time.time() - t, 3)

        # ── Step 7.5: Run pytest suite in sandbox ──────────────────
        t = time.time()
        # module_name already computed above — reused here
        logs.append("[7.5] Running equivalent pytest suite in sandbox …")
        test_results = sandbox_pytest(
            module_code=exec_info["final_code"],
            test_code=pytest_data.get("test_code", ""),
            module_name=module_name,
            timeout=PYTEST_SANDBOX_TIMEOUT,
        )
        n_pass = len(test_results["passed"])
        n_fail = len(test_results["failed"])
        logs.append(f"      [OK] {test_results['summary']}  [{round(time.time()-t,3)}s]")
        timings["pytest_run"] = round(time.time() - t, 3)

        # ── Step 8: Explainability Analysis ─────────────────────────
        t = time.time()
        logs.append("[8/8] Running explainability analysis …")

        # Extract debug_log early so the XAI partial result can use it
        debug_log = exec_info["debug_log"]

        # Build partial result for XAI (before xai key exists)
        _partial_result = {
            "python_code": exec_info["final_code"],
            "result": {
                "status": "SUCCESS" if validation["is_valid"] else "PARTIAL",
                "confidence_score": compute_confidence(
                    exec_info["_debug_result"], {"pass_rate": validation["pass_rate"]}
                ),
                "debug_passed": exec_info["debug_passed"],
                "iterations": exec_info["iterations"],
                "complexity": route,
            },
            "validation": validation,
            "timing": timings,
            "test_results": test_results,
            "agents": {  # minimal agent data for XAI
                "expert_1_structure": {
                    "program_id": analysis.get("program_id", "UNKNOWN"),
                    "complexity": "complex" if any([
                        analysis.get("has_file_io"),
                        analysis.get("has_occurs"),
                        analysis.get("has_redefines"),
                        analysis.get("line_count", 0) > 40,
                    ]) else "simple",
                    "paragraphs": analysis.get("paragraphs", []),
                    "model": "rule-based (no LLM)",
                    "status": "success",
                    "file_io": analysis.get("has_file_io", False),
                },
                "expert_2_router": {
                    "model": "SmolLM via Ollama (rule-based fallback)",
                    "decision": route,
                    "reason": "complex signals detected" if route == "complex"
                               else "no complex signals",
                    "status": "success",
                },
                "expert_3_translation": {
                    "model": "Groq llama-3.3-70b-versatile",
                    "chars": len(exec_info["final_code"]),
                    "lines": len(exec_info["final_code"].splitlines()),
                    "status": "success",
                },
                "expert_4_debug": {
                    "model": "Groq llama-3.3-70b-versatile (escalation) + rule-based",
                    "iterations": exec_info["iterations"],
                    "log": [
                        {
                            "iteration": r.iteration,
                            "error_type": r.error_type,
                            "fix_applied": r.fix_applied,
                            "status": r.status,
                        }
                        for r in debug_log
                    ],
                    "status": "success" if exec_info["debug_passed"] else "failed",
                },
                "expert_5_validation": {
                    "model": "rule-based (no LLM)",
                    "pass_rate": 1.0 if validation["pass_rate"] == 100 else 0.0,
                    "status": "success" if validation["pass_rate"] == 100 else "failed",
                },
            },
            "logs": logs,
        }
        xai_data = generate_xai_report(_partial_result, preprocessed["cleaned_source"])
        xai_elapsed = round(time.time() - t, 3)
        timings["xai_analysis"] = xai_elapsed
        logs.append(f"      [OK] XAI report generated  [{xai_elapsed:.3f}s]")


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
            "confidence":    confidence,  # top-level alias for UI
            "validation":    validation,
            "timing":        timings,
            "test_results":  test_results,   # sandbox_pytest structured output
            "pytest_data":   pytest_data,    # raw test_code + test_cases metadata
            "xai":           xai_data,       # explainability report
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
