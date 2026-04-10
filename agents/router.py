"""Router — Expert 2. Uses SmolLM via Ollama to classify task complexity."""

import re
import requests
from config import SMOLLM_BASE_URL, SMOLLM_MODEL


ROUTER_PROMPT = """You are a COBOL complexity classifier.
Read the COBOL program and reply with exactly one word: simple or complex.

simple  = no nested PERFORMs, no file I/O, no OCCURS, under 40 lines
complex = has any of: nested PERFORMs, file I/O, OCCURS tables, REDEFINES, GO TO, over 40 lines

Reply with only the single word. No punctuation. No explanation."""


def classify(cobol_code: str, structured_analysis: dict = None) -> str:
    """
    Returns "simple" or "complex".
    Falls back to rule-based if SmolLM is unavailable.
    """
    # Try SmolLM via Ollama first
    try:
        payload = {
            "model":  SMOLLM_MODEL,
            "prompt": f"{ROUTER_PROMPT}\n\nCOBOL:\n{cobol_code[:1500]}",
            "stream": False,
            "options": {"num_predict": 5, "temperature": 0}
        }
        resp = requests.post(
            f"{SMOLLM_BASE_URL}/api/generate",
            json=payload,
            timeout=10
        )
        if resp.status_code == 200:
            answer = resp.json().get("response", "").strip().lower()
            if "simple" in answer:
                return "simple"
            if "complex" in answer:
                return "complex"
    except Exception:
        pass  # Fall through to rule-based

    # Rule-based fallback — always available, no model needed
    return _rule_based(cobol_code, structured_analysis)


def _rule_based(cobol_code: str, analysis: dict = None) -> str:
    """Deterministic fallback classifier."""
    if analysis:
        complexity = analysis.get("complexity", "").lower()
        if complexity in ("simple", "complex"):
            return complexity

    code_upper = cobol_code.upper()
    lines      = [l for l in cobol_code.splitlines() if l.strip()]

    complex_signals = [
        len(lines) > 40,
        "OCCURS"     in code_upper,
        "REDEFINES"  in code_upper,
        "GO TO"      in code_upper,
        "FILE-CONTROL" in code_upper,
        "SELECT"     in code_upper,
        "FD "        in code_upper,
        code_upper.count("PERFORM") > 3,
        "COMP-3"     in code_upper,
        "EVALUATE"   in code_upper,
    ]

    return "complex" if any(complex_signals) else "simple"
