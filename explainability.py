"""Explainable AI (XAI) module for COBOL-to-Python migration pipeline.

Performs post-hoc analysis of pipeline results to produce transparent,
interpretable reports explaining *why* each translation decision was made,
*which* components contributed, and *how* confident the system is at each stage.

No additional LLM calls — pure analysis of existing pipeline state.

Usage:
    from explainability import ExplainabilityAnalyzer
    xai = ExplainabilityAnalyzer(pipeline_result)
    report = xai.analyze()
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any


# =====================================================================
#  Data structures
# =====================================================================

@dataclass
class ConfidenceDecomposition:
    """Interpretable sub-scores that compose the overall confidence."""
    syntax_validity: float = 0.0       # Did code pass AST parsing?
    execution_stability: float = 0.0   # Did code run without crashes?
    test_coverage: float = 0.0         # What fraction of tests passed?
    debug_convergence: float = 0.0     # How quickly did debug loop converge?
    rag_relevance: float = 0.0         # Were KB docs actually used?
    overall: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentContribution:
    """Weighted contribution of a single pipeline expert."""
    name: str
    role: str
    model: str
    contribution_score: float  # 0.0–1.0
    status: str
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TranslationPattern:
    """A COBOL construct mapped to a Python idiom."""
    cobol_construct: str
    python_idiom: str
    category: str  # e.g., "control_flow", "data_type", "file_io"
    detected: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiskIndicator:
    """A potential issue flagged by the XAI analysis."""
    severity: str       # "low", "medium", "high"
    category: str
    message: str
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DebugIterationDetail:
    """Analysis of a single debug loop iteration."""
    iteration: int
    error_type: str
    fix_strategy: str   # "rule_based" or "llm_escalation"
    fix_description: str
    resolved: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionTrace:
    """Per-paragraph mapping of COBOL → Python decisions."""
    paragraph_name: str
    cobol_statements: int
    python_mapped: bool
    patterns_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class XAIReport:
    """Complete explainability report for one pipeline run."""
    program_id: str = ""
    pipeline_status: str = ""
    confidence_decomposition: ConfidenceDecomposition = field(default_factory=ConfidenceDecomposition)
    agent_contributions: list[AgentContribution] = field(default_factory=list)
    decision_trace: list[DecisionTrace] = field(default_factory=list)
    translation_patterns: list[TranslationPattern] = field(default_factory=list)
    rag_influence: dict[str, Any] = field(default_factory=dict)
    debug_analysis: dict[str, Any] = field(default_factory=dict)
    risk_indicators: list[RiskIndicator] = field(default_factory=list)
    summary_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "pipeline_status": self.pipeline_status,
            "confidence_decomposition": self.confidence_decomposition.to_dict(),
            "agent_contributions": [a.to_dict() for a in self.agent_contributions],
            "decision_trace": [d.to_dict() for d in self.decision_trace],
            "translation_patterns": [p.to_dict() for p in self.translation_patterns],
            "rag_influence": self.rag_influence,
            "debug_analysis": self.debug_analysis,
            "risk_indicators": [r.to_dict() for r in self.risk_indicators],
            "summary_text": self.summary_text,
        }


# =====================================================================
#  Pattern detection rules
# =====================================================================

_COBOL_PATTERNS = [
    ("PERFORM VARYING",    "for loop (range-based)",      "control_flow"),
    ("PERFORM UNTIL",      "while loop",                  "control_flow"),
    ("EVALUATE",           "if/elif/else chain",          "control_flow"),
    ("GO TO",              "function call + return",      "control_flow"),
    ("READ",               "readline() with EOF check",   "file_io"),
    ("WRITE",              "file.write()",                "file_io"),
    ("OPEN INPUT",         "open() for reading",          "file_io"),
    ("OPEN OUTPUT",        "open() for writing",          "file_io"),
    ("CLOSE",              "file.close()",                "file_io"),
    ("OCCURS",             "list of dicts",               "data_structure"),
    ("REDEFINES",          "helper conversion function",  "data_structure"),
    ("COMP-3",             "Decimal type",                "data_type"),
    ("PIC S9",             "Decimal type",                "data_type"),
    ("PIC 9",              "int type",                    "data_type"),
    ("PIC X",              "str type",                    "data_type"),
    ("MOVE",               "variable assignment",         "assignment"),
    ("ADD",                "+= operator",                 "arithmetic"),
    ("SUBTRACT",           "-= operator",                 "arithmetic"),
    ("COMPUTE",            "arithmetic expression",       "arithmetic"),
    ("STRING DELIMITED",   "string concatenation",        "string_ops"),
    ("FILE-CONTROL",       "file path constants",         "file_io"),
    ("WORKING-STORAGE",    "module-level globals",        "data_structure"),
    ("STOP RUN",           "sys.exit(0) in __main__",     "control_flow"),
]


# =====================================================================
#  Analyzer
# =====================================================================

class ExplainabilityAnalyzer:
    """Post-hoc explainability analyzer for pipeline results.

    Takes a complete pipeline result dict (from ``run_pipeline()``) and
    the original COBOL source, then produces an ``XAIReport``.
    """

    def __init__(
        self,
        pipeline_result: dict[str, Any],
        cobol_source: str = "",
    ) -> None:
        self._result = pipeline_result
        self._cobol = cobol_source
        self._agents = pipeline_result.get("agents", {})
        self._res = pipeline_result.get("result", {})
        self._timing = pipeline_result.get("timing", {})
        self._validation = pipeline_result.get("validation", {})
        self._python_code = pipeline_result.get("python_code", "")
        self._test_results = pipeline_result.get("test_results", {})

    def analyze(self) -> XAIReport:
        """Run full explainability analysis and return structured report."""
        report = XAIReport()

        # Basic info
        struct = self._agents.get("expert_1_structure", {})
        report.program_id = struct.get("program_id", "UNKNOWN")
        report.pipeline_status = self._res.get("status", "UNKNOWN")

        # Sub-analyses
        report.confidence_decomposition = self._decompose_confidence()
        report.agent_contributions = self._analyze_agents()
        report.decision_trace = self._build_decision_trace()
        report.translation_patterns = self._detect_patterns()
        report.rag_influence = self._analyze_rag()
        report.debug_analysis = self._analyze_debug()
        report.risk_indicators = self._detect_risks()
        report.summary_text = self._generate_summary(report)

        return report

    # ── Confidence decomposition ──────────────────────────────────

    def _decompose_confidence(self) -> ConfidenceDecomposition:
        cd = ConfidenceDecomposition()
        overall = self._res.get("confidence_score", 0)
        cd.overall = overall

        # Syntax validity: did code parse?
        has_code = bool(self._python_code.strip())
        cd.syntax_validity = 100.0 if has_code else 0.0

        # Execution stability: did sandbox pass?
        cd.execution_stability = 100.0 if self._res.get("debug_passed") else 0.0

        # Test coverage
        passed = len(self._test_results.get("passed", []))
        failed = len(self._test_results.get("failed", []))
        total = passed + failed
        cd.test_coverage = (passed / total * 100) if total > 0 else 0.0

        # Debug convergence: fewer iterations = higher score
        iters = self._res.get("iterations", 0)
        max_iter = 7
        if self._res.get("debug_passed"):
            cd.debug_convergence = max(0, (1.0 - (iters - 1) / max_iter)) * 100
        else:
            cd.debug_convergence = 0.0

        # RAG relevance: were KB docs injected?
        rag_info = self._analyze_rag()
        cd.rag_relevance = 100.0 if rag_info.get("kb_docs_injected", 0) > 0 else 30.0

        return cd

    # ── Agent contributions ───────────────────────────────────────

    def _analyze_agents(self) -> list[AgentContribution]:
        contributions = []
        total_time = self._timing.get("total", 1) or 1

        # Expert 1: Structure
        s = self._agents.get("expert_1_structure", {})
        struct_time = self._timing.get("structure", 0)
        contributions.append(AgentContribution(
            name="Structure Analyst",
            role="COBOL parsing & structural analysis",
            model=s.get("model", "rule-based"),
            contribution_score=round(struct_time / total_time, 3),
            status=s.get("status", "unknown"),
            details=f"Extracted {len(s.get('paragraphs', []))} paragraphs, "
                    f"complexity={s.get('complexity', 'N/A')}",
        ))

        # Expert 2: Router
        r = self._agents.get("expert_2_router", {})
        router_time = self._timing.get("router", 0)
        contributions.append(AgentContribution(
            name="SLM Router",
            role="Complexity classification (simple/complex)",
            model=r.get("model", "SmolLM"),
            contribution_score=round(router_time / total_time, 3),
            status=r.get("status", "unknown"),
            details=f"Decision: {r.get('decision', 'N/A')} — {r.get('reason', '')}",
        ))

        # Expert 3: Translation
        t = self._agents.get("expert_3_translation", {})
        trans_time = self._timing.get("translation", 0)
        contributions.append(AgentContribution(
            name="Translation Engine",
            role="COBOL→Python code generation",
            model=t.get("model", "Groq LLM"),
            contribution_score=round(trans_time / total_time, 3),
            status=t.get("status", "unknown"),
            details=f"Generated {t.get('chars', 0)} chars / {t.get('lines', 0)} lines",
        ))

        # Expert 4: Debug
        d = self._agents.get("expert_4_debug", {})
        exec_time = self._timing.get("execution", 0)
        contributions.append(AgentContribution(
            name="Debug Expert",
            role="Self-debugging & error correction",
            model=d.get("model", "Groq LLM + rule-based"),
            contribution_score=round(exec_time / total_time, 3),
            status=d.get("status", "unknown"),
            details=f"{d.get('iterations', 0)} iteration(s) used",
        ))

        # Expert 5: Validation
        v = self._agents.get("expert_5_validation", {})
        val_time = self._timing.get("validation", 0)
        contributions.append(AgentContribution(
            name="Validator",
            role="Final correctness gate",
            model=v.get("model", "rule-based"),
            contribution_score=round(val_time / total_time, 3),
            status=v.get("status", "unknown"),
            details=f"Pass rate: {v.get('pass_rate', 0):.0%}",
        ))

        return contributions

    # ── Decision trace ────────────────────────────────────────────

    def _build_decision_trace(self) -> list[DecisionTrace]:
        struct = self._agents.get("expert_1_structure", {})
        paragraphs = struct.get("paragraphs", [])
        code_lower = self._python_code.lower()
        traces = []

        for para in paragraphs:
            py_name = para.lower().replace("-", "_")
            mapped = py_name in code_lower or f"def {py_name}" in code_lower

            # Detect which patterns apply to this paragraph
            patterns = []
            if self._cobol:
                # Find paragraph body in COBOL source
                para_pattern = re.compile(
                    rf'{re.escape(para)}\.\s*\n(.*?)(?=\n\s*\w[\w-]*\.\s*$|\Z)',
                    re.MULTILINE | re.DOTALL | re.IGNORECASE,
                )
                match = para_pattern.search(self._cobol)
                if match:
                    body = match.group(1).upper()
                    for kw, idiom, _ in _COBOL_PATTERNS:
                        if kw in body:
                            patterns.append(f"{kw} → {idiom}")

            traces.append(DecisionTrace(
                paragraph_name=para,
                cobol_statements=0,  # simplified
                python_mapped=mapped,
                patterns_used=patterns,
            ))

        return traces

    # ── Translation pattern detection ─────────────────────────────

    def _detect_patterns(self) -> list[TranslationPattern]:
        if not self._cobol:
            return []

        cobol_upper = self._cobol.upper()
        detected = []
        for keyword, idiom, category in _COBOL_PATTERNS:
            if keyword in cobol_upper:
                detected.append(TranslationPattern(
                    cobol_construct=keyword,
                    python_idiom=idiom,
                    category=category,
                    detected=True,
                ))
        return detected

    # ── RAG influence ─────────────────────────────────────────────

    def _analyze_rag(self) -> dict[str, Any]:
        logs = self._result.get("logs", [])
        kb_count = 0
        for log in logs:
            if "[RAG]" in log and "KB document" in log:
                # Extract count from log line
                m = re.search(r'(\d+)\s+KB document', log)
                if m:
                    kb_count = int(m.group(1))
                break

        rag_time = self._timing.get("rag", 0)

        return {
            "kb_docs_injected": kb_count,
            "rag_build_time_s": rag_time,
            "influence_level": "high" if kb_count >= 3 else ("medium" if kb_count >= 1 else "none"),
            "description": (
                f"{kb_count} knowledge base document(s) were injected into "
                f"the translation prompt to provide cross-module reference context."
                if kb_count > 0 else
                "No KB documents were available — translation relied solely on the LLM's training data."
            ),
        }

    # ── Debug analysis ────────────────────────────────────────────

    def _analyze_debug(self) -> dict[str, Any]:
        debug_agent = self._agents.get("expert_4_debug", {})
        debug_log = debug_agent.get("log", [])
        iterations = debug_agent.get("iterations", 0)

        iteration_details = []
        rule_fixes = 0
        llm_fixes = 0

        for entry in debug_log:
            fix = entry.get("fix_applied", "")
            is_llm = "escalated" in fix.lower() or "deepseek" in fix.lower()
            if is_llm:
                llm_fixes += 1
                strategy = "llm_escalation"
            else:
                rule_fixes += 1
                strategy = "rule_based"

            iteration_details.append(DebugIterationDetail(
                iteration=entry.get("iteration", 0),
                error_type=entry.get("error_type", "unknown"),
                fix_strategy=strategy,
                fix_description=fix,
                resolved=entry.get("status") in ("pass", "fixed"),
            ).to_dict())

        converged = self._res.get("debug_passed", False)

        return {
            "total_iterations": iterations,
            "converged": converged,
            "rule_based_fixes": rule_fixes,
            "llm_escalation_fixes": llm_fixes,
            "convergence_description": (
                f"Debug loop converged in {iterations} iteration(s). "
                f"{rule_fixes} fix(es) were rule-based (free, instant), "
                f"{llm_fixes} required LLM escalation."
                if converged else
                f"Debug loop did NOT converge after {iterations} iteration(s). "
                f"The code may still contain errors."
            ),
            "iterations": iteration_details,
        }

    # ── Risk detection ────────────────────────────────────────────

    def _detect_risks(self) -> list[RiskIndicator]:
        risks = []
        if not self._cobol:
            return risks

        cobol_upper = self._cobol.upper()
        code = self._python_code

        # Risk: REDEFINES without helper function
        if "REDEFINES" in cobol_upper and "_as_char" not in code and "redefines" not in code.lower():
            risks.append(RiskIndicator(
                severity="high", category="data_structure",
                message="COBOL REDEFINES detected but no conversion helper function found in Python output.",
                suggestion="Verify that REDEFINES fields are correctly handled with type conversion functions.",
            ))

        # Risk: COMP-3 without Decimal
        if "COMP-3" in cobol_upper and "Decimal" not in code:
            risks.append(RiskIndicator(
                severity="high", category="data_type",
                message="COMP-3 packed decimal fields detected but no Decimal import in Python output.",
                suggestion="Ensure COMP-3 fields use Python's Decimal type to avoid floating-point errors.",
            ))

        # Risk: File I/O without error handling
        if "FILE-CONTROL" in cobol_upper and "try" not in code:
            risks.append(RiskIndicator(
                severity="medium", category="file_io",
                message="COBOL file operations detected but no try/except error handling in Python output.",
                suggestion="Add try/except blocks around file operations to handle missing files gracefully.",
            ))

        # Risk: GO TO detected
        if "GO TO" in cobol_upper:
            risks.append(RiskIndicator(
                severity="medium", category="control_flow",
                message="COBOL GO TO statements detected — these are hard to translate correctly.",
                suggestion="Verify the translated control flow matches the original GO TO branching logic.",
            ))

        # Risk: Debug loop didn't converge
        if not self._res.get("debug_passed", False):
            risks.append(RiskIndicator(
                severity="high", category="execution",
                message="Debug loop did not converge — translated code may contain runtime errors.",
                suggestion="Review the debug log for unresolved errors and consider manual fixes.",
            ))

        # Risk: No test coverage
        passed = len(self._test_results.get("passed", []))
        failed = len(self._test_results.get("failed", []))
        if passed + failed == 0:
            risks.append(RiskIndicator(
                severity="medium", category="testing",
                message="No pytest results available — code correctness is unverified.",
                suggestion="Generate and run test cases to validate the translated code's behavior.",
            ))

        # Risk: Large COBOL program (context truncation)
        line_count = len([l for l in self._cobol.splitlines() if l.strip()])
        if line_count > 100:
            risks.append(RiskIndicator(
                severity="medium", category="complexity",
                message=f"Large COBOL program ({line_count} lines) — may exceed LLM context window.",
                suggestion="Check for missing paragraphs or truncated data divisions in the output.",
            ))

        # Risk: No RAG context
        rag = self._analyze_rag()
        if rag.get("kb_docs_injected", 0) == 0:
            risks.append(RiskIndicator(
                severity="low", category="rag",
                message="No knowledge base documents were injected into the translation prompt.",
                suggestion="Add relevant COBOL→Python migration patterns to data/knowledge_base/.",
            ))

        return risks

    # ── Summary generation ────────────────────────────────────────

    def _generate_summary(self, report: XAIReport) -> str:
        cd = report.confidence_decomposition
        n_patterns = len(report.translation_patterns)
        n_risks = len(report.risk_indicators)
        high_risks = sum(1 for r in report.risk_indicators if r.severity == "high")
        n_paragraphs = len(report.decision_trace)
        mapped = sum(1 for d in report.decision_trace if d.python_mapped)

        lines = [
            f"Program {report.program_id} — {report.pipeline_status}",
            f"Overall confidence: {cd.overall:.1f}%",
            f"  Syntax: {cd.syntax_validity:.0f}% | Execution: {cd.execution_stability:.0f}% | "
            f"Tests: {cd.test_coverage:.0f}% | Debug: {cd.debug_convergence:.0f}% | "
            f"RAG: {cd.rag_relevance:.0f}%",
            f"Paragraphs: {mapped}/{n_paragraphs} mapped to Python functions",
            f"Translation patterns detected: {n_patterns}",
            f"Risk indicators: {n_risks} ({high_risks} high severity)",
        ]

        debug = report.debug_analysis
        if debug.get("converged"):
            lines.append(
                f"Debug loop converged in {debug['total_iterations']} iteration(s) "
                f"({debug['rule_based_fixes']} rule-based, {debug['llm_escalation_fixes']} LLM)"
            )
        else:
            lines.append("⚠ Debug loop did NOT converge")

        return "\n".join(lines)


# =====================================================================
#  Convenience function
# =====================================================================

def generate_xai_report(
    pipeline_result: dict[str, Any],
    cobol_source: str = "",
) -> dict[str, Any]:
    """One-call convenience: analyze and return dict."""
    analyzer = ExplainabilityAnalyzer(pipeline_result, cobol_source)
    report = analyzer.analyze()
    return report.to_dict()
