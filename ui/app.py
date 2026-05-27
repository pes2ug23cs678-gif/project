"""
Streamlit UI for the COBOL → Python Migration Pipeline.

Launch:
    streamlit run ui/app.py
"""

from __future__ import annotations

import sys
import os
import time

# ── Ensure project root is on sys.path ────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
from main import run_pipeline, SAMPLE_COBOL


# ======================================================================
#  Page Config
# ======================================================================

st.set_page_config(
    page_title="COBOL → Python Migrator",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ======================================================================
#  Minimal, clean CSS
# ======================================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Clean divider-style header bar */
.header-bar {
    border-left: 4px solid #667eea;
    padding-left: 1rem;
    margin-bottom: 1.5rem;
}
.header-bar h1 {
    font-size: 1.6rem;
    font-weight: 600;
    margin: 0;
    color: #e0e0e0;
}
.header-bar p {
    font-size: 0.9rem;
    color: #888;
    margin: 0.2rem 0 0 0;
}

/* Status pill */
.status-pill {
    display: inline-block;
    padding: 0.3rem 0.9rem;
    border-radius: 20px;
    font-weight: 600;
    font-size: 0.85rem;
    letter-spacing: 0.3px;
}
.pill-success { background: #065f46; color: #6ee7b7; }
.pill-partial { background: #78350f; color: #fcd34d; }
.pill-failed  { background: #7f1d1d; color: #fca5a5; }
.pill-error   { background: #7f1d1d; color: #fca5a5; }
</style>
""", unsafe_allow_html=True)


# ======================================================================
#  Sidebar — Input & Settings
# ======================================================================

with st.sidebar:
    st.markdown("## ⚙️ Settings")

    input_method = st.radio(
        "Input method",
        ["🧪 Sample", "📝 Paste", "📁 Upload"],
        horizontal=True,
    )

    st.divider()

    max_retries = st.slider("Debug retries", 1, 5, 3)
    show_agent_json = st.toggle("Show raw agent JSON", value=False)

    st.divider()
    st.caption("COBOL → Python Migrator v1.0")


# ======================================================================
#  Header
# ======================================================================

st.markdown("""
<div class="header-bar">
    <h1>🔄 COBOL → Python Migrator</h1>
    <p>Multi-agent translation with self-debugging &amp; validation</p>
</div>
""", unsafe_allow_html=True)


# ======================================================================
#  Input Area
# ======================================================================

cobol_source = ""

if input_method == "📝 Paste":
    cobol_source = st.text_area(
        "Paste COBOL source code",
        height=280,
        placeholder="       IDENTIFICATION DIVISION.\n       PROGRAM-ID. HELLO.\n       ...",
    )

elif input_method == "📁 Upload":
    uploaded = st.file_uploader(
        "Upload .cob / .cbl / .cobol file",
        type=["cob", "cbl", "cobol", "cpy", "txt"],
    )
    if uploaded:
        cobol_source = uploaded.read().decode("utf-8")
        with st.expander("Preview uploaded file"):
            st.code(cobol_source, language="cobol", line_numbers=True)

else:  # Sample
    cobol_source = SAMPLE_COBOL
    with st.expander("📄 PAYROLL sample program", expanded=True):
        st.code(cobol_source, language="cobol", line_numbers=True)


# ======================================================================
#  Run Button
# ======================================================================

can_run = bool(cobol_source and cobol_source.strip())

if st.button("🚀 Run Pipeline", type="primary", disabled=not can_run):

    with st.spinner("Running migration pipeline…"):
        t0 = time.perf_counter()
        result = run_pipeline(cobol_source)
        wall = time.perf_counter() - t0

    st.session_state["result"]      = result
    st.session_state["last_result"] = result   # Agents tab reads this
    st.session_state["wall"]        = wall


# ======================================================================
#  Results
# ======================================================================

if "result" not in st.session_state:
    st.stop()

result = st.session_state["result"]
wall = st.session_state.get("wall", 0)
res = result.get("result", {})
timing = result.get("timing", {})
status = res.get("status", "UNKNOWN")

st.divider()

# ── Status pill ───────────────────────────────────────────────────────

pill_cls = {"SUCCESS": "pill-success", "PARTIAL": "pill-partial",
            "FAILED": "pill-failed", "ERROR": "pill-error"}.get(status, "pill-failed")
pill_icon = {"SUCCESS": "✅", "PARTIAL": "⚠️", "FAILED": "❌", "ERROR": "💥"}.get(status, "❓")

st.markdown(f'<span class="status-pill {pill_cls}">{pill_icon} {status}</span>', unsafe_allow_html=True)
st.markdown("")

# ── Metrics row ───────────────────────────────────────────────────────

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Confidence", f"{res.get('confidence_score', 0):.1f}%")
c2.metric("Complexity", res.get("complexity", "N/A"))
c3.metric("Iterations", res.get("iterations", 0))
c4.metric("Debug Loop", "Pass ✓" if res.get("debug_passed") else "Fail ✗")
c5.metric("Total Time", f"{timing.get('total', wall):.2f}s")


# ── Tabs ──────────────────────────────────────────────────────────────

tab_code, tab_logs, tab_timing, tab_valid, tab_tests, tab_agents, tab_xai = st.tabs(
    ["🐍 Code", "📋 Logs", "⏱ Timing", "🛡 Validation", "🧪 Test Cases", "🤖 Agents", "🔍 XAI"]
)

# ── Code tab ──────────────────────────────────────────────────────────

with tab_code:
    code = result.get("python_code", "")
    if code.strip():
        st.code(code, language="python", line_numbers=True)
        st.download_button("📥 Download .py", code, "translated.py", "text/x-python")
    else:
        st.warning("No code generated — see Logs tab.")


# ── Logs tab ──────────────────────────────────────────────────────────

with tab_logs:
    logs = result.get("logs", [])
    if logs:
        st.code("\n".join(logs), language="text")
    else:
        st.info("No logs.")


# ── Timing tab ────────────────────────────────────────────────────────

with tab_timing:
    result = st.session_state.get("last_result", {})
    timing = result.get("timing", {})

    if not timing:
        st.info("No timing data yet.")
    else:
        stage_config = {
            "preprocess":  ("🔍", "Preprocess"),
            "structure":   ("🧱", "Structure Analysis"),
            "rag":         ("📚", "RAG Context"),
            "router":      ("🧭", "Router (SmolLM)"),
            "translation": ("⚙️",  "Translation (Groq)"),
            "execution":   ("🐛", "Sandbox + Debug Loop"),
            "validation":  ("✅", "Validation"),
            "xai_analysis":("🔍", "XAI Analysis"),
        }
        total = timing.get("total", 0) or 1  # guard against zero-div

        for key, (icon, label) in stage_config.items():
            val = timing.get(key, 0)
            pct = val / total if total > 0 else 0
            col1, col2, col3 = st.columns([2, 6, 1])
            with col1:
                st.markdown(f"{icon} **{label}**")
            with col2:
                st.progress(min(pct, 1.0))
            with col3:
                st.markdown(f"`{val}s`")

        st.markdown(f"**Total: {timing.get('total', 0)}s**")


# ── Validation tab ────────────────────────────────────────────────────

with tab_valid:
    validation = result.get("validation", {})
    if validation:
        if validation.get("is_valid"):
            st.success(f"✅ Valid — {validation.get('reason', '')}")
        else:
            st.error(f"❌ Invalid — {validation.get('reason', '')}")

        conf = validation.get("confidence_score", 0)
        st.progress(int(conf), text=f"Confidence: {conf:.0f}%")

        with st.expander("Full report"):
            st.json(validation.get("report", {}))
    else:
        err = res.get("error", "")
        if err:
            st.error(f"Pipeline error: {err}")
        else:
            st.info("No validation data.")


# ── Test Cases tab ────────────────────────────────────────────────────

with tab_tests:
    test_results = result.get("test_results", {})
    pytest_data  = result.get("pytest_data", {})

    if not test_results and not pytest_data:
        st.info("No test data yet — run the pipeline first.")
    else:
        passed_list = test_results.get("passed", [])
        failed_list = test_results.get("failed", [])
        error_list  = test_results.get("errors", [])
        summary_str = test_results.get("summary", "")
        total_tests = len(passed_list) + len(failed_list)

        # ── Headline metrics ────────────────────────────────────────
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("✅ Passed",  len(passed_list))
        mc2.metric("❌ Failed",  len(failed_list))
        mc3.metric("⚠️ Errors",  len(error_list))
        mc4.metric("Total",      total_tests)

        if summary_str:
            badge = "✅" if not failed_list and not error_list else "⚠️"
            st.markdown(f"**{badge} {summary_str}**")

        st.divider()

        # ── Per-test cards ──────────────────────────────────────────
        all_tests = (
            [(n, True)  for n in passed_list] +
            [(n, False) for n in failed_list]
        )

        if all_tests:
            st.markdown("#### Test Results")
            for node, is_passed in all_tests:
                icon  = "✅" if is_passed else "❌"
                label = "PASSED" if is_passed else "FAILED"
                with st.expander(f"{icon} `{node}` — **{label}**", expanded=False):
                    st.markdown(f"**Status:** `{label}`")
                    # Show which COBOL test case this maps to (if available)
                    test_cases = pytest_data.get("test_cases", [])
                    fn_name = node.split("::")[-1] if "::" in node else node
                    for tc in test_cases:
                        if tc.get("name") == fn_name:
                            st.markdown(f"**Category:** `{tc.get('category', 'N/A')}`")
                            st.markdown(f"**Description:** {tc.get('description', '')}")
                            if tc.get("inputs"):
                                st.json(tc["inputs"])
                            break
        else:
            st.info("No individual test results to display (collection may have failed).")

        # ── Collection errors ───────────────────────────────────────
        if error_list:
            st.markdown("#### ⚠️ Collection / Import Errors")
            for err in error_list:
                st.error(err)

        # ── Raw pytest output ───────────────────────────────────────
        raw_stdout = test_results.get("stdout", "")
        if raw_stdout:
            with st.expander("📄 Raw pytest output"):
                st.code(raw_stdout, language="text")

        # ── Download generated test file ────────────────────────────
        test_code = pytest_data.get("test_code", "")
        if test_code:
            st.divider()
            st.markdown("#### 📥 Download Generated Test File")
            module_id = result.get("agents", {}).get(
                "expert_1_structure", {}
            ).get("program_id", "program").lower().replace("-", "_")
            st.download_button(
                "⬇️ Download pytest file",
                test_code,
                file_name=f"test_{module_id}.py",
                mime="text/x-python",
            )
            with st.expander("👁 Preview test file"):
                st.code(test_code, language="python", line_numbers=True)


# ── Agents tab ────────────────────────────────────────────────────────

with tab_agents:
    result = st.session_state.get("last_result", {})
    agents = result.get("agents", {})

    if not agents:
        st.info("No agent data. Run the pipeline first.")
    else:
        agent_order = [
            "expert_1_structure",
            "expert_2_router",
            "expert_3_translation",
            "expert_4_debug",
            "expert_5_validation",
        ]
        icons = {
            "expert_1_structure":   "🔍",
            "expert_2_router":      "🧭",
            "expert_3_translation": "⚙️",
            "expert_4_debug":       "🐛",
            "expert_5_validation":  "✅",
        }
        for key in agent_order:
            data = agents.get(key, {})
            if not data:
                continue
            status      = data.get("status", "unknown")
            status_icon = "✅" if status == "success" else "❌"
            icon        = icons.get(key, "🤖")

            with st.expander(
                f"{icon} {data.get('name', key)}  —  {status_icon} {status.upper()}",
                expanded=(key == "expert_4_debug")
            ):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Model:** `{data.get('model', 'N/A')}`")
                with col2:
                    st.markdown(f"**Status:** `{status}`")

                if key == "expert_1_structure":
                    st.markdown(f"**Program:** `{data.get('program_id')}`")
                    st.markdown(f"**Complexity:** `{data.get('complexity')}`")
                    st.markdown(f"**File I/O:** `{data.get('file_io')}`")
                    paras = data.get("paragraphs", [])
                    if paras:
                        st.markdown(
                            f"**Paragraphs ({len(paras)}):** "
                            + ", ".join(paras if isinstance(paras, list) else list(paras))
                        )

                elif key == "expert_2_router":
                    st.markdown(f"**Decision:** `{data.get('decision')}`")
                    st.markdown(f"**Reason:** {data.get('reason')}")

                elif key == "expert_3_translation":
                    st.markdown(
                        f"**Output size:** "
                        f"`{data.get('chars')} chars / "
                        f"{data.get('lines')} lines`"
                    )

                elif key == "expert_4_debug":
                    st.markdown(f"**Iterations used:** `{data.get('iterations')}`")
                    debug_log = data.get("log", [])
                    if debug_log:
                        st.markdown("**Iteration log:**")
                        for entry in debug_log:
                            log_icon = "✅" if entry["status"] in ("pass", "fixed") else "❌"
                            st.markdown(
                                f"- {log_icon} **Iter {entry['iteration']}** | "
                                f"Error: `{entry['error_type']}` | "
                                f"Fix: {entry['fix_applied']}"
                            )

                elif key == "expert_5_validation":
                    passed = data.get("passed", 0)
                    total  = data.get("total", 0)
                    rate   = data.get("pass_rate", 0.0)
                    st.markdown(f"**Tests passed:** `{passed}/{total}`")
                    st.progress(float(rate))

        if show_agent_json:
            st.subheader("🔎 Raw Agent JSON")
            st.json(agents)


# ── XAI tab ───────────────────────────────────────────────────────────

with tab_xai:
    xai = result.get("xai", {})

    if not xai:
        st.info("No explainability data yet — run the pipeline first.")
    else:
        import json as _json

        st.markdown("### 🔍 Explainable AI Report")
        st.caption(f"Program: **{xai.get('program_id', 'N/A')}** — Status: **{xai.get('pipeline_status', 'N/A')}**")

        # ── 1. Confidence Decomposition ────────────────────────────
        st.markdown("#### 📊 Confidence Decomposition")
        cd = xai.get("confidence_decomposition", {})
        overall = cd.get("overall", 0)

        st.markdown(f"**Overall Confidence: {overall:.1f}%**")
        st.progress(min(int(overall), 100))

        sub_scores = [
            ("Syntax Validity",      cd.get("syntax_validity", 0)),
            ("Execution Stability",  cd.get("execution_stability", 0)),
            ("Test Coverage",        cd.get("test_coverage", 0)),
            ("Debug Convergence",    cd.get("debug_convergence", 0)),
            ("RAG Relevance",        cd.get("rag_relevance", 0)),
        ]
        cols = st.columns(5)
        for col, (label, score) in zip(cols, sub_scores):
            col.metric(label, f"{score:.0f}%")

        st.divider()

        # ── 2. Agent Contributions ─────────────────────────────────
        st.markdown("#### 🤖 Agent Contributions")
        agents_xai = xai.get("agent_contributions", [])
        if agents_xai:
            for agent in agents_xai:
                score_pct = agent.get("contribution_score", 0) * 100
                status_icon = "✅" if agent.get("status") == "success" else "❌"
                with st.expander(
                    f"{status_icon} **{agent['name']}** — {score_pct:.1f}% of pipeline time",
                    expanded=False,
                ):
                    st.markdown(f"**Role:** {agent.get('role', '')}")
                    st.markdown(f"**Model:** `{agent.get('model', 'N/A')}`")
                    st.markdown(f"**Details:** {agent.get('details', '')}")
                    st.progress(min(score_pct / 100, 1.0))

        st.divider()

        # ── 3. Decision Trace ──────────────────────────────────────
        st.markdown("#### 🗺️ Decision Trace (Paragraph Mapping)")
        traces = xai.get("decision_trace", [])
        if traces:
            for tr in traces:
                mapped_icon = "✅" if tr.get("python_mapped") else "⚠️"
                patterns = tr.get("patterns_used", [])
                pattern_str = ", ".join(patterns) if patterns else "no specific patterns"
                with st.expander(
                    f"{mapped_icon} `{tr['paragraph_name']}` — {'Mapped' if tr.get('python_mapped') else 'NOT mapped'}",
                    expanded=False,
                ):
                    st.markdown(f"**COBOL→Python patterns:** {pattern_str}")
        else:
            st.info("No paragraphs detected.")

        st.divider()

        # ── 4. Translation Patterns ────────────────────────────────
        st.markdown("#### 🔄 Detected Translation Patterns")
        patterns = xai.get("translation_patterns", [])
        if patterns:
            categories = {}
            for p in patterns:
                cat = p.get("category", "other")
                categories.setdefault(cat, []).append(p)
            for cat, items in sorted(categories.items()):
                st.markdown(f"**{cat.replace('_', ' ').title()}:**")
                for item in items:
                    st.markdown(
                        f"- `{item['cobol_construct']}` → *{item['python_idiom']}*"
                    )
        else:
            st.info("No patterns detected.")

        st.divider()

        # ── 5. RAG Influence ───────────────────────────────────────
        st.markdown("#### 📚 RAG Influence")
        rag = xai.get("rag_influence", {})
        rc1, rc2, rc3 = st.columns(3)
        rc1.metric("KB Docs Injected", rag.get("kb_docs_injected", 0))
        rc2.metric("Influence Level", rag.get("influence_level", "none").capitalize())
        rc3.metric("RAG Build Time", f"{rag.get('rag_build_time_s', 0):.3f}s")
        st.markdown(rag.get("description", ""))

        st.divider()

        # ── 6. Debug Analysis ──────────────────────────────────────
        st.markdown("#### 🐛 Debug Loop Analysis")
        debug = xai.get("debug_analysis", {})
        converged = debug.get("converged", False)
        dc1, dc2, dc3, dc4 = st.columns(4)
        dc1.metric("Iterations", debug.get("total_iterations", 0))
        dc2.metric("Converged", "Yes ✓" if converged else "No ✗")
        dc3.metric("Rule Fixes", debug.get("rule_based_fixes", 0))
        dc4.metric("LLM Fixes", debug.get("llm_escalation_fixes", 0))
        st.markdown(debug.get("convergence_description", ""))

        debug_iters = debug.get("iterations", [])
        if debug_iters:
            st.markdown("**Iteration Timeline:**")
            for it in debug_iters:
                r_icon = "✅" if it.get("resolved") else "❌"
                st.markdown(
                    f"- {r_icon} **Iter {it['iteration']}** | "
                    f"Error: `{it['error_type']}` | "
                    f"Strategy: `{it['fix_strategy']}` | "
                    f"{it['fix_description']}"
                )

        st.divider()

        # ── 7. Risk Indicators ─────────────────────────────────────
        st.markdown("#### ⚠️ Risk Indicators")
        risks = xai.get("risk_indicators", [])
        if risks:
            for risk in risks:
                sev = risk.get("severity", "low")
                if sev == "high":
                    st.error(f"🔴 **{risk['category'].upper()}** — {risk['message']}")
                elif sev == "medium":
                    st.warning(f"🟡 **{risk['category'].upper()}** — {risk['message']}")
                else:
                    st.info(f"🔵 **{risk['category'].upper()}** — {risk['message']}")
                if risk.get("suggestion"):
                    st.caption(f"💡 {risk['suggestion']}")
        else:
            st.success("No risks detected — translation looks clean!")

        st.divider()

        # ── 8. Summary & Download ──────────────────────────────────
        st.markdown("#### 📝 Summary")
        st.code(xai.get("summary_text", ""), language="text")

        st.download_button(
            "📥 Download XAI Report (JSON)",
            _json.dumps(xai, indent=2, default=str),
            file_name=f"xai_report_{xai.get('program_id', 'program').lower()}.json",
            mime="application/json",
        )
