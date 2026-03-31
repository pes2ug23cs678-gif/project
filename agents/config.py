"""Centralized configuration, enums, and constants for the agents package."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Complexity(str, enum.Enum):
    """Task complexity classification."""

    SIMPLE = "simple"
    COMPLEX = "complex"


class Severity(int, enum.Enum):
    """Debug-fix difficulty rating."""

    TRIVIAL = 1
    LOW = 2
    MODERATE = 3
    HIGH = 4
    CRITICAL = 5

    @property
    def label(self) -> str:
        return _SEVERITY_LABELS[self]


_SEVERITY_LABELS: dict[Severity, str] = {
    Severity.TRIVIAL: "Trivial fix",
    Severity.LOW: "Low complexity",
    Severity.MODERATE: "Moderate complexity",
    Severity.HIGH: "Complex — requires careful analysis",
    Severity.CRITICAL: "Critical — deep logic error",
}


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RouterConfig:
    """Tunable weights for the complexity scoring heuristic."""

    division_weight: float = 1.0
    perform_weight: float = 2.0
    external_weight: float = 3.0
    line_count_weight: float = 0.01
    complexity_threshold: float = 6.0


@dataclass(frozen=True)
class PipelineConfig:
    """Top-level pipeline settings."""

    max_debug_retries: int = 3
    router: RouterConfig = field(default_factory=RouterConfig)


# ---------------------------------------------------------------------------
# COBOL keyword blacklist (shared across experts)
# ---------------------------------------------------------------------------

COBOL_KEYWORDS: frozenset[str] = frozenset({
    "ACCEPT", "ADD", "CALL", "CLOSE", "COMPUTE", "CONTINUE",
    "DELETE", "DISPLAY", "DIVIDE", "ELSE", "END-EVALUATE",
    "END-IF", "EVALUATE", "EXIT", "GO", "IF", "INITIALIZE",
    "INSPECT", "MERGE", "MOVE", "MULTIPLY", "OPEN", "PERFORM",
    "READ", "RELEASE", "RETURN", "REWRITE", "SEARCH", "SET",
    "SORT", "START", "STOP", "STRING", "SUBTRACT", "UNSTRING",
    "WRITE",
})

# ---------------------------------------------------------------------------
# Error-type → base severity mapping
# ---------------------------------------------------------------------------

ERROR_SEVERITY: dict[str, Severity] = {
    "SyntaxError": Severity.LOW,
    "IndentationError": Severity.TRIVIAL,
    "NameError": Severity.LOW,
    "TypeError": Severity.MODERATE,
    "ValueError": Severity.MODERATE,
    "IndexError": Severity.MODERATE,
    "KeyError": Severity.LOW,
    "AttributeError": Severity.MODERATE,
    "ZeroDivisionError": Severity.MODERATE,
    "ImportError": Severity.TRIVIAL,
    "FileNotFoundError": Severity.LOW,
    "OverflowError": Severity.HIGH,
    "RuntimeError": Severity.HIGH,
    "AssertionError": Severity.MODERATE,
    "LogicError": Severity.CRITICAL,
}
