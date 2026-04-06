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

    st.session_state["result"] = result
    st.session_state["wall"] = wall


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
c1.metric("Confidence", f"{res.get('confidence_score', 0):.0f}%")
c2.metric("Complexity", res.get("complexity", "N/A"))
c3.metric("Iterations", res.get("iterations", 0))
c4.metric("Debug Loop", "Pass ✓" if res.get("debug_passed") else "Fail ✗")
c5.metric("Total Time", f"{timing.get('total', wall):.2f}s")


# ── Tabs ──────────────────────────────────────────────────────────────

tab_code, tab_logs, tab_timing, tab_valid, tab_agents = st.tabs(
    ["🐍 Code", "📋 Logs", "⏱ Timing", "🛡 Validation", "🤖 Agents"]
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
    if timing:
        total = timing.get("total", 1) or 1
        stages = [
            ("🔍 Preprocess",  "preprocess"),
            ("📚 RAG Context", "rag_context"),
            ("🤖 Agents",      "agents"),
            ("🐛 Execution",   "execution"),
            ("✅ Validation",  "validation"),
        ]
        for label, key in stages:
            secs = timing.get(key, 0)
            pct = secs / total
            col_l, col_bar, col_t = st.columns([1.2, 4, 0.8])
            col_l.markdown(f"**{label}**")
            col_bar.progress(min(pct, 1.0))
            col_t.code(f"{secs:.3f}s")

        st.markdown(f"**Total: {total:.3f}s**")
    else:
        st.info("No timing data.")


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


# ── Agents tab ────────────────────────────────────────────────────────

with tab_agents:
    agent_out = result.get("agent_output", {})
    if not agent_out:
        st.info("No agent data. Run the pipeline first.")
        st.stop()

    # Routing
    routing = agent_out.get("routing", {})
    if routing:
        st.subheader("🔀 Routing")
        rc1, rc2, rc3 = st.columns(3)
        rc1.metric("Complexity", routing.get("complexity", "—"))
        rc2.metric("Score", routing.get("score", 0))
        rc3.metric("Flow", " → ".join(routing.get("recommended_flow", [])) or "—")

        with st.expander("Scoring dimensions"):
            st.json(routing.get("dimensions", {}))

    # Structure
    structure = agent_out.get("structure", {})
    if structure:
        st.subheader("🏗 Structure")
        sc1, sc2 = st.columns(2)
        sc1.markdown(f"**Program ID:** `{structure.get('program_id', '—')}`")
        divs = structure.get("divisions", [])
        sc1.markdown(f"**Divisions:** {', '.join(divs) or '—'}")
        paras = structure.get("paragraphs", [])
        sc2.markdown(f"**Paragraphs:** {', '.join(paras) or '—'}")
        sc2.markdown(f"**Data Items:** {len(structure.get('data_items', []))}")

        if structure.get("flow_summary"):
            with st.expander("Flow summary"):
                st.code(structure["flow_summary"], language="text")

    # Mapping table
    translation = agent_out.get("translation", {})
    mapping = translation.get("mapping_table", [])
    if mapping:
        st.subheader("🗺 Construct Mapping")
        import pandas as pd
        st.dataframe(pd.DataFrame(mapping), width="stretch", hide_index=True)

    # Test cases
    tests = agent_out.get("tests", {})
    cases = tests.get("test_cases", [])
    if cases:
        st.subheader(f"🧪 Test Cases ({len(cases)})")
        for tc in cases:
            icon = {"happy_path": "😊", "boundary": "📏", "error": "💥",
                    "type_check": "🔠"}.get(tc.get("category", ""), "•")
            with st.expander(f"{icon} {tc['name']}"):
                st.markdown(f"**Target:** `{tc.get('target_function', '')}()`")
                st.markdown(tc.get("description", ""))

    # Debug history
    debug_hist = agent_out.get("debug_history", [])
    if debug_hist:
        st.subheader(f"🐛 Debug History ({len(debug_hist)})")
        for e in debug_hist:
            st.markdown(
                f"**Iter {e.get('iteration', '?')}:** "
                f"`{e.get('error_type', '—')}` (sev {e.get('severity', '?')}/5) "
                f"— {e.get('error_summary', e.get('remaining_error', ''))}"
            )

    # Raw JSON
    if show_agent_json:
        st.subheader("🔎 Raw JSON")
        st.json(agent_out)
