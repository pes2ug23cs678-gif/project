"""
Streamlit UI for the COBOL → Python Migration Pipeline.

Launch:
    streamlit run ui/app.py
"""

from __future__ import annotations

import sys
import os
import time
import logging

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
#  Premium CSS
# ======================================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.header-bar {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    border-radius: 12px;
    padding: 1.5rem 2rem;
    margin-bottom: 1.5rem;
    border: 1px solid rgba(102,126,234,0.3);
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
.header-bar h1 { font-size: 1.8rem; font-weight: 700; margin: 0; color: #e0e0e0; }
.header-bar p { font-size: 0.95rem; color: #94a3b8; margin: 0.3rem 0 0 0; }

.status-pill {
    display: inline-block; padding: 0.35rem 1rem; border-radius: 20px;
    font-weight: 600; font-size: 0.85rem; letter-spacing: 0.5px;
}
.pill-success { background: #065f46; color: #6ee7b7; border: 1px solid #10b981; }
.pill-partial { background: #78350f; color: #fcd34d; border: 1px solid #f59e0b; }
.pill-failed  { background: #7f1d1d; color: #fca5a5; border: 1px solid #ef4444; }
.pill-error   { background: #7f1d1d; color: #fca5a5; border: 1px solid #ef4444; }

.step-card {
    background: rgba(30,41,59,0.5); border-radius: 8px; padding: 0.8rem 1rem;
    margin: 0.4rem 0; border-left: 3px solid #667eea;
    font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; color: #cbd5e1;
}
.step-ok   { border-left-color: #10b981; }
.step-fail { border-left-color: #ef4444; }
.step-run  { border-left-color: #f59e0b; }

.metric-card {
    background: linear-gradient(135deg, rgba(30,41,59,0.6), rgba(15,52,96,0.4));
    border: 1px solid rgba(102,126,234,0.2); border-radius: 10px;
    padding: 1rem; text-align: center;
}
</style>
""", unsafe_allow_html=True)


# ======================================================================
#  Sidebar
# ======================================================================

with st.sidebar:
    st.markdown("## ⚙️ Settings")
    input_method = st.radio("Input method", ["🧪 Sample", "📝 Paste", "📁 Upload"], horizontal=True)
    st.divider()
    show_agent_json = st.toggle("Show raw agent JSON", value=False)
    st.divider()
    st.caption("COBOL → Python Migrator v2.0")
    st.caption("Multi-agent · Self-debugging · Explainable")


# ======================================================================
#  Header
# ======================================================================

st.markdown("""
<div class="header-bar">
    <h1>🔄 COBOL → Python Migrator</h1>
    <p>Multi-agent translation with self-debugging, test generation &amp; explainability</p>
</div>
""", unsafe_allow_html=True)


# ======================================================================
#  Input Area
# ======================================================================

cobol_source = ""

if input_method == "📝 Paste":
    cobol_source = st.text_area(
        "Paste COBOL source code", height=280,
        placeholder="       IDENTIFICATION DIVISION.\n       PROGRAM-ID. HELLO.\n       ...",
    )
elif input_method == "📁 Upload":
    uploaded = st.file_uploader("Upload .cob / .cbl / .cobol file", type=["cob", "cbl", "cobol", "cpy", "txt"])
    if uploaded:
        cobol_source = uploaded.read().decode("utf-8")
        with st.expander("📄 Preview uploaded file"):
            st.code(cobol_source, language="cobol", line_numbers=True)
else:
    cobol_source = SAMPLE_COBOL
    with st.expander("📄 Sample COBOL program (ENTERPRISE-LEDGER-SYSTEM)", expanded=True):
        st.code(cobol_source, language="cobol", line_numbers=True)


# ======================================================================
#  Run Button
# ======================================================================

can_run = bool(cobol_source and cobol_source.strip())

if st.button("🚀 Run Migration Pipeline", type="primary", disabled=not can_run, use_container_width=True):

    # ── Live progress display ─────────────────────────────────────
    progress_bar = st.progress(0, text="Initializing pipeline...")
    log_container = st.container()

    class StreamlitLogHandler(logging.Handler):
        """Captures pipeline log messages and updates the progress bar."""
        def __init__(self, progress, container):
            super().__init__()
            self.progress = progress
            self.container = container
            self.step_map = {
                "Preprocessing": 10, "Preprocessing complete": 15,
                "COBOL scenario": 20, "Routing": 25,
                "RAG": 35, "Translating": 45, "Translation:": 55,
                "pytest suite": 60, "Running sandbox": 65,
                "Debug loop": 80, "validation": 90,
            }
        def emit(self, record):
            msg = self.format(record)
            for keyword, pct in self.step_map.items():
                if keyword.lower() in msg.lower():
                    self.progress.progress(pct, text=f"🔄 {msg}")
                    break

    pipeline_logger = logging.getLogger("pipeline")
    handler = StreamlitLogHandler(progress_bar, log_container)
    handler.setFormatter(logging.Formatter('%(message)s'))
    pipeline_logger.addHandler(handler)
    pipeline_logger.setLevel(logging.INFO)

    t0 = time.perf_counter()
    try:
        result = run_pipeline(cobol_source)
    finally:
        pipeline_logger.removeHandler(handler)

    wall = time.perf_counter() - t0
    status = result.get("result", {}).get("status", "UNKNOWN")
    icon = "✅" if status == "SUCCESS" else "⚠️" if status == "PARTIAL" else "❌"
    progress_bar.progress(100, text=f"{icon} Pipeline complete in {wall:.1f}s — {status}")

    st.session_state["result"] = result
    st.session_state["wall"] = wall


# ======================================================================
#  Results
# ======================================================================

if "result" not in st.session_state:
    st.info("👆 Select your COBOL source and click **Run Migration Pipeline** to begin.")
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
    ["🐍 Code", "📋 Pipeline Log", "⏱ Timing", "🛡 Validation", "🧪 Tests", "🤖 Agents", "🔍 XAI"]
)

# ── Code tab ──────────────────────────────────────────────────────────
with tab_code:
    code = result.get("python_code", "")
    if code.strip():
        st.markdown(f"**Generated Python** — `{len(code.splitlines())}` lines, `{len(code)}` chars")
        st.code(code, language="python", line_numbers=True)
        col_dl1, col_dl2 = st.columns(2)
        col_dl1.download_button("📥 Download .py", code, "translated.py", "text/x-python", use_container_width=True)
    else:
        st.warning("No code generated — check the Pipeline Log tab for errors.")

# ── Logs tab ──────────────────────────────────────────────────────────
with tab_logs:
    logs = result.get("logs", [])
    if logs:
        for log_line in logs:
            if "[OK]" in log_line:
                css_class = "step-ok"
            elif "[FAIL]" in log_line or "[ERROR]" in log_line:
                css_class = "step-fail"
            elif log_line.startswith("[") or log_line.startswith("  "):
                css_class = "step-run"
            elif "=" * 10 in log_line:
                st.divider()
                continue
            else:
                css_class = ""
            if css_class:
                st.markdown(f'<div class="step-card {css_class}">{log_line}</div>', unsafe_allow_html=True)
            else:
                st.markdown(log_line)
    else:
        st.info("No logs available.")

# ── Timing tab ────────────────────────────────────────────────────────
with tab_timing:
    if not timing:
        st.info("No timing data yet.")
    else:
        stage_config = {
            "preprocess":      ("🔍", "Preprocess"),
            "structure":       ("🧱", "Structure Analysis"),
            "cobol_scenarios": ("📋", "COBOL Scenarios"),
            "rag":             ("📚", "RAG Context"),
            "router":          ("🧭", "Router (SmolLM)"),
            "translation":     ("⚙️",  "Translation (LLM)"),
            "pytest_gen":      ("🧪", "Test Generation"),
            "execution":       ("🐛", "Sandbox + Debug"),
            "validation":      ("✅", "Validation"),
            "pytest_run":      ("🧪", "Pytest Execution"),
            "xai_analysis":    ("🔍", "XAI Analysis"),
        }
        total = timing.get("total", 0) or 1

        for key, (icon, label) in stage_config.items():
            val = timing.get(key, 0)
            if val == 0 and key not in timing:
                continue
            pct = val / total if total > 0 else 0
            col1, col2, col3 = st.columns([2, 6, 1])
            with col1:
                st.markdown(f"{icon} **{label}**")
            with col2:
                st.progress(min(pct, 1.0))
            with col3:
                st.markdown(f"`{val:.2f}s`")

        st.markdown(f"**Total: {timing.get('total', 0):.2f}s**")

# ── Validation tab ────────────────────────────────────────────────────
with tab_valid:
    validation = result.get("validation", {})
    if validation:
        is_valid = validation.get("is_valid", False)
        confidence = res.get("confidence_score", 0)

        if is_valid:
            st.success("✅ Code is valid — runs without errors in sandbox")
        else:
            stderr_preview = validation.get("stderr", "").strip()
            last_line = stderr_preview.splitlines()[-1] if stderr_preview else "unknown error"
            st.error(f"❌ Validation failed — {last_line}")

        st.progress(min(int(confidence), 100), text=f"Confidence: {confidence:.1f}%")

        col_v1, col_v2, col_v3 = st.columns(3)
        col_v1.metric("Pass Rate", f"{validation.get('pass_rate', 0)}%")
        col_v2.metric("Exit Code", validation.get("returncode", "N/A"))
        col_v3.metric("Confidence", f"{confidence:.1f}%")

        stdout = validation.get("stdout", "")
        stderr = validation.get("stderr", "")
        if stdout.strip():
            with st.expander("📤 Program stdout"):
                st.code(stdout, language="text")
        if stderr.strip():
            with st.expander("⚠️ Program stderr"):
                st.code(stderr, language="text")
    else:
        err = res.get("error", "")
        if err:
            st.error(f"Pipeline error: {err}")
        else:
            st.info("No validation data.")

# ── Test Cases tab ────────────────────────────────────────────────────
with tab_tests:
    test_results = result.get("test_results", {})
    pytest_data = result.get("pytest_data", {})

    if not test_results and not pytest_data:
        st.info("No test data — run the pipeline first.")
    else:
        passed_list = test_results.get("passed", [])
        failed_list = test_results.get("failed", [])
        error_list = test_results.get("errors", [])
        summary_str = test_results.get("summary", "")
        total_tests = len(passed_list) + len(failed_list)

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("✅ Passed", len(passed_list))
        mc2.metric("❌ Failed", len(failed_list))
        mc3.metric("⚠️ Errors", len(error_list))
        mc4.metric("Total", total_tests)

        if summary_str:
            badge = "✅" if not failed_list and not error_list else "⚠️"
            st.markdown(f"**{badge} {summary_str}**")

        st.divider()

        all_tests = ([(n, True) for n in passed_list] + [(n, False) for n in failed_list])
        if all_tests:
            st.markdown("#### Test Results")
            for node, is_passed in all_tests:
                icon = "✅" if is_passed else "❌"
                label = "PASSED" if is_passed else "FAILED"
                st.markdown(f"{icon} `{node}` — **{label}**")

        if error_list:
            st.markdown("#### ⚠️ Collection / Import Errors")
            for err in error_list:
                st.error(err)

        raw_stdout = test_results.get("stdout", "")
        if raw_stdout:
            with st.expander("📄 Raw pytest output"):
                st.code(raw_stdout, language="text")

        test_code = pytest_data.get("test_code", "")
        if test_code:
            st.divider()
            st.download_button("⬇️ Download pytest file", test_code, file_name="test_migrated.py", mime="text/x-python")
            with st.expander("👁 Preview test file"):
                st.code(test_code, language="python", line_numbers=True)

# ── Agents tab ────────────────────────────────────────────────────────
with tab_agents:
    agents = result.get("agents", {})
    if not agents:
        st.info("No agent data. Run the pipeline first.")
    else:
        agent_order = [
            "expert_1_structure", "expert_2_router", "expert_3_translation",
            "expert_4_debug", "expert_5_validation",
        ]
        icons = {
            "expert_1_structure": "🔍", "expert_2_router": "🧭",
            "expert_3_translation": "⚙️", "expert_4_debug": "🐛",
            "expert_5_validation": "✅",
        }
        for key in agent_order:
            data = agents.get(key, {})
            if not data:
                continue
            agent_status = data.get("status", "unknown")
            status_icon = "✅" if agent_status == "success" else "❌"
            icon = icons.get(key, "🤖")

            with st.expander(f"{icon} {data.get('name', key)}  —  {status_icon} {agent_status.upper()}", expanded=(key == "expert_4_debug")):
                col1, col2 = st.columns(2)
                col1.markdown(f"**Model:** `{data.get('model', 'N/A')}`")
                col2.markdown(f"**Status:** `{agent_status}`")

                if key == "expert_1_structure":
                    st.markdown(f"**Program:** `{data.get('program_id')}`  |  **Complexity:** `{data.get('complexity')}`  |  **File I/O:** `{data.get('file_io')}`")
                    paras = data.get("paragraphs", [])
                    if paras:
                        st.markdown(f"**Paragraphs ({len(paras)}):** {', '.join(paras if isinstance(paras, list) else list(paras))}")
                elif key == "expert_2_router":
                    st.markdown(f"**Decision:** `{data.get('decision')}`  |  **Reason:** {data.get('reason')}")
                elif key == "expert_3_translation":
                    st.markdown(f"**Output:** `{data.get('chars')} chars / {data.get('lines')} lines`")
                elif key == "expert_4_debug":
                    st.markdown(f"**Iterations used:** `{data.get('iterations')}`")
                    debug_log = data.get("log", [])
                    if debug_log:
                        for entry in debug_log:
                            log_icon = "✅" if entry.get("status") in ("pass", "fixed") else "❌"
                            st.markdown(f"- {log_icon} **Iter {entry.get('iteration')}** | Error: `{entry.get('error_type')}` | Fix: {entry.get('fix_applied')}")
                elif key == "expert_5_validation":
                    rate = data.get("pass_rate", 0.0)
                    st.markdown(f"**Tests passed:** `{data.get('passed', 0)}/{data.get('total', 0)}`")
                    st.progress(float(rate))

        if show_agent_json:
            st.subheader("🔎 Raw Agent JSON")
            st.json(agents)

# ── XAI tab ───────────────────────────────────────────────────────────
with tab_xai:
    xai = result.get("xai", {})
    if not xai:
        st.info("No explainability data — run the pipeline first.")
    else:
        import json as _json

        st.markdown("### 🔍 Explainable AI Report")
        st.caption(f"Program: **{xai.get('program_id', 'N/A')}** — Status: **{xai.get('pipeline_status', 'N/A')}**")

        # Confidence
        st.markdown("#### 📊 Confidence Decomposition")
        cd = xai.get("confidence_decomposition", {})
        overall = cd.get("overall", 0)
        st.markdown(f"**Overall Confidence: {overall:.1f}%**")
        st.progress(min(int(overall), 100))

        sub_scores = [
            ("Syntax", cd.get("syntax_validity", 0)),
            ("Execution", cd.get("execution_stability", 0)),
            ("Tests", cd.get("test_coverage", 0)),
            ("Debug", cd.get("debug_convergence", 0)),
            ("RAG", cd.get("rag_relevance", 0)),
        ]
        cols = st.columns(5)
        for col, (label, score) in zip(cols, sub_scores):
            col.metric(label, f"{score:.0f}%")

        st.divider()

        # Agent Contributions
        st.markdown("#### 🤖 Agent Contributions")
        for agent in xai.get("agent_contributions", []):
            score_pct = agent.get("contribution_score", 0) * 100
            s_icon = "✅" if agent.get("status") == "success" else "❌"
            with st.expander(f"{s_icon} **{agent['name']}** — {score_pct:.1f}% of pipeline time"):
                st.markdown(f"**Role:** {agent.get('role', '')}  |  **Model:** `{agent.get('model', 'N/A')}`")
                st.markdown(f"**Details:** {agent.get('details', '')}")

        st.divider()

        # Decision Trace
        traces = xai.get("decision_trace", [])
        if traces:
            st.markdown("#### 🗺️ Decision Trace (Paragraph Mapping)")
            for tr in traces:
                mapped_icon = "✅" if tr.get("python_mapped") else "⚠️"
                patterns = tr.get("patterns_used", [])
                pattern_str = ", ".join(patterns) if patterns else "none"
                st.markdown(f"- {mapped_icon} `{tr['paragraph_name']}` → Patterns: {pattern_str}")
            st.divider()

        # Translation Patterns
        patterns = xai.get("translation_patterns", [])
        if patterns:
            st.markdown("#### 🔄 Translation Patterns")
            categories = {}
            for p in patterns:
                categories.setdefault(p.get("category", "other"), []).append(p)
            for cat, items in sorted(categories.items()):
                st.markdown(f"**{cat.replace('_', ' ').title()}:**")
                for item in items:
                    st.markdown(f"- `{item['cobol_construct']}` → *{item['python_idiom']}*")
            st.divider()

        # Debug Analysis
        debug = xai.get("debug_analysis", {})
        st.markdown("#### 🐛 Debug Loop Analysis")
        dc1, dc2, dc3, dc4 = st.columns(4)
        dc1.metric("Iterations", debug.get("total_iterations", 0))
        dc2.metric("Converged", "Yes ✓" if debug.get("converged") else "No ✗")
        dc3.metric("Rule Fixes", debug.get("rule_based_fixes", 0))
        dc4.metric("LLM Fixes", debug.get("llm_escalation_fixes", 0))
        st.markdown(debug.get("convergence_description", ""))

        st.divider()

        # Risks
        risks = xai.get("risk_indicators", [])
        st.markdown("#### ⚠️ Risk Indicators")
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

        # Summary & Download
        st.markdown("#### 📝 Summary")
        st.code(xai.get("summary_text", ""), language="text")
        st.download_button(
            "📥 Download XAI Report (JSON)",
            _json.dumps(xai, indent=2, default=str),
            file_name=f"xai_report_{xai.get('program_id', 'program').lower()}.json",
            mime="application/json",
        )
