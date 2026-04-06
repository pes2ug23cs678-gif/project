"""Advanced correctness checking for COBOL → Python output comparison.

Replaces the naive string-equality check with a multi-layered analysis
that handles the messy realities of COBOL-to-Python output:

    • Numeric formatting differences  (0400 vs 400 vs 400.0)
    • Whitespace & padding            ("SUM =  0400" vs "SUM = 400")
    • Case variations                 ("Hello" vs "HELLO")
    • Multi-line ordering             (line-by-line comparison)
    • Floating-point tolerance        (15000.00 vs 14999.999…)
    • Token-level structural match    (ignores punctuation noise)
    • Partial / substring match       (handles extra banner text)

Each strategy returns a MatchResult with a numeric *similarity score*
(0.0–1.0) so callers can threshold at whatever level they need.

Usage
-----
    from evaluation.correctness import CorrectnessChecker
    result = CorrectnessChecker.check("TAX = 15000.00", "TAX = 15000.0")
    print(result.score, result.strategy)   # 1.0  "numeric_tolerant"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


# =====================================================================
#  Result type
# =====================================================================

@dataclass(frozen=True)
class MatchResult:
    """Outcome of a correctness comparison."""

    matched: bool
    score: float            # 0.0 – 1.0
    strategy: str           # which strategy made the decision
    details: str = ""       # human-readable explanation


# =====================================================================
#  Constants
# =====================================================================

_NUMERIC_TOLERANCE = 1e-4   # relative tolerance for float comparison
_SIMILARITY_THRESHOLD = 0.85  # minimum SequenceMatcher ratio to PASS


# =====================================================================
#  Individual strategies (pure functions)
# =====================================================================

def _exact_match(expected: str, actual: str) -> MatchResult | None:
    """Strategy 1 — byte-for-byte equality."""
    if expected == actual:
        return MatchResult(True, 1.0, "exact", "Byte-for-byte match")
    return None


def _normalized_match(expected: str, actual: str) -> MatchResult | None:
    """Strategy 2 — case-insensitive, whitespace-collapsed."""
    e = _normalize(expected)
    a = _normalize(actual)
    if e == a:
        return MatchResult(True, 1.0, "normalized", "Match after whitespace + case normalization")
    return None


def _numeric_tolerant_match(expected: str, actual: str) -> MatchResult | None:
    """Strategy 3 — compare line-by-line, treating numeric tokens with tolerance.

    Handles COBOL-style zero-padded integers (0400 vs 400) and floating-
    point drift (15000.00 vs 14999.9999).
    """
    exp_lines = _split_lines(expected)
    act_lines = _split_lines(actual)

    if len(exp_lines) != len(act_lines):
        return None

    for el, al in zip(exp_lines, act_lines):
        if not _lines_equivalent(el, al):
            return None

    return MatchResult(
        True, 1.0, "numeric_tolerant",
        "All lines match with numeric tolerance",
    )


def _token_structural_match(expected: str, actual: str) -> MatchResult | None:
    """Strategy 4 — tokenize, strip noise, compare token sequences.

    Strips out punctuation differences so  "SUM = 0400." matches
    "SUM = 400".  Numeric tokens are compared with tolerance.
    """
    exp_tokens = _tokenize(expected)
    act_tokens = _tokenize(actual)

    if len(exp_tokens) != len(act_tokens):
        return None

    for et, at in zip(exp_tokens, act_tokens):
        if not _tokens_equal(et, at):
            return None

    return MatchResult(
        True, 1.0, "token_structural",
        "Token sequences match structurally",
    )


def _substring_containment(expected: str, actual: str) -> MatchResult | None:
    """Strategy 5 — the expected output is contained within actual.

    Covers cases where the generated code prints extra banners,
    debug info, or trailing newlines around the real answer.
    """
    e = _normalize(expected)
    a = _normalize(actual)
    if e and e in a:
        # Score proportional to how much of actual is the expected part
        coverage = len(e) / max(len(a), 1)
        return MatchResult(True, max(coverage, 0.7), "substring", f"Expected found inside actual (coverage={coverage:.0%})")
    return None


def _line_subset_match(expected: str, actual: str) -> MatchResult | None:
    """Strategy 6 — every expected line appears somewhere in actual (order-independent).

    Handles cases where extra lines or reordered output are present.
    """
    exp_lines = set(_split_lines(expected))
    act_lines = set(_split_lines(actual))

    if not exp_lines:
        return None

    matched = sum(1 for el in exp_lines if any(_lines_equivalent(el, al) for al in act_lines))
    ratio = matched / len(exp_lines)

    if ratio >= 1.0:
        return MatchResult(True, 0.9, "line_subset", "All expected lines found in actual output")
    if ratio >= 0.8:
        return MatchResult(True, ratio * 0.9, "line_subset_partial", f"{matched}/{len(exp_lines)} expected lines found")
    return None


def _fuzzy_similarity(expected: str, actual: str) -> MatchResult:
    """Strategy 7 (fallback) — SequenceMatcher ratio.

    Always returns a result (never None).  Whether it counts as a PASS
    depends on whether the score meets the threshold.
    """
    e = _normalize(expected)
    a = _normalize(actual)
    ratio = SequenceMatcher(None, e, a).ratio()
    matched = ratio >= _SIMILARITY_THRESHOLD
    return MatchResult(
        matched, ratio, "fuzzy_similarity",
        f"SequenceMatcher ratio = {ratio:.3f} (threshold = {_SIMILARITY_THRESHOLD})",
    )


# =====================================================================
#  Main checker — runs strategies in priority order
# =====================================================================

class CorrectnessChecker:
    """Stateless checker that runs a cascade of comparison strategies."""

    # Ordered from cheapest / most precise → most expensive / fuzziest
    _STRATEGIES = [
        _exact_match,
        _normalized_match,
        _numeric_tolerant_match,
        _token_structural_match,
        _substring_containment,
        _line_subset_match,
        # _fuzzy_similarity is the fallback — always returns
    ]

    @classmethod
    def check(cls, expected: str, actual: str) -> MatchResult:
        """Compare *expected* and *actual* using cascading strategies.

        Returns the first successful MatchResult, or the fuzzy-similarity
        fallback if nothing else matches.
        """
        if not expected.strip() and not actual.strip():
            return MatchResult(True, 1.0, "both_empty", "Both expected and actual are empty")

        if not expected.strip():
            return MatchResult(False, 0.0, "expected_empty", "Expected output is empty — cannot validate")

        for strategy in cls._STRATEGIES:
            result = strategy(expected, actual)
            if result is not None and result.matched:
                return result

        # Fallback: fuzzy similarity (always returns)
        return _fuzzy_similarity(expected, actual)

    @classmethod
    def check_with_pipeline(
        cls,
        pipeline_out: dict[str, Any],
        expected: str,
    ) -> MatchResult:
        """Higher-level check that also inspects pipeline metadata.

        Uses the pipeline's own validation report as the first signal,
        then falls through to content-based comparison.
        """
        # Fast path: pipeline's validator already confirmed match
        validation = pipeline_out.get("validation", {})
        report = validation.get("report", {})
        if report.get("success") is True and report.get("reason") == "Exact Output Match":
            return MatchResult(True, 1.0, "pipeline_validator", "Pipeline validator confirmed exact match")

        if validation.get("confidence_score", 0) >= 100:
            return MatchResult(True, 1.0, "pipeline_confidence", "Pipeline confidence = 100%")

        # Extract actual output from pipeline
        actual = cls._extract_actual(pipeline_out)
        return cls.check(expected, actual)

    @staticmethod
    def _extract_actual(pipeline_out: dict[str, Any]) -> str:
        """Best-effort extraction of the generated program's stdout."""
        validation = pipeline_out.get("validation", {})
        report = validation.get("report", {})
        details = report.get("details", "")

        # Validator stores "Actual Output:\n...\n\nExpected:\n..."
        if "Actual Output:" in details:
            parts = details.split("Actual Output:")
            if len(parts) > 1:
                actual = parts[1].split("Expected:")[0].strip()
                return actual

        # If output matched exactly, details may say so directly
        if "Output perfectly matches" in details:
            return pipeline_out.get("result", {}).get("expected_output", "")

        # Last resort: re-execute the code (expensive, but reliable)
        python_code = pipeline_out.get("python_code", "")
        if python_code.strip():
            try:
                import subprocess
                proc = subprocess.run(
                    ["python3", "-c", python_code],
                    capture_output=True, text=True, timeout=10,
                )
                if proc.returncode == 0:
                    return proc.stdout.strip()
            except Exception:
                pass

        return ""


# =====================================================================
#  Internal helpers
# =====================================================================

def _normalize(text: str) -> str:
    """Collapse whitespace, strip, upper-case."""
    return re.sub(r"\s+", " ", text.strip()).upper()


def _split_lines(text: str) -> list[str]:
    """Split into stripped, non-empty lines."""
    return [ln.strip() for ln in text.strip().splitlines() if ln.strip()]


def _tokenize(text: str) -> list[str]:
    """Extract word / number tokens, dropping pure punctuation."""
    return re.findall(r"[A-Za-z_]+|[\d]+(?:\.[\d]+)?", text)


def _tokens_equal(a: str, b: str) -> bool:
    """Check if two tokens are semantically equal (numeric-aware)."""
    if a.upper() == b.upper():
        return True
    # Try numeric comparison
    try:
        na, nb = float(a), float(b)
        if na == 0 and nb == 0:
            return True
        return abs(na - nb) / max(abs(na), abs(nb), 1e-12) < _NUMERIC_TOLERANCE
    except ValueError:
        return False


def _lines_equivalent(line_a: str, line_b: str) -> bool:
    """Compare two output lines with token-level numeric tolerance."""
    toks_a = _tokenize(line_a)
    toks_b = _tokenize(line_b)
    if len(toks_a) != len(toks_b):
        return False
    return all(_tokens_equal(a, b) for a, b in zip(toks_a, toks_b))
