"""Abstract base class for all expert modules."""

from __future__ import annotations

import abc
import logging
from typing import Any


class BaseExpert(abc.ABC):
    """Common interface and utilities shared by every expert.

    Subclasses must implement :meth:`run`, which accepts domain-specific
    arguments and returns a ``dict[str, Any]``.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}",
        )

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def run(self, **kwargs: Any) -> dict[str, Any]:
        """Execute the expert's analysis and return structured results."""

    # ------------------------------------------------------------------
    # Shared validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def validate_source(source: str, label: str = "cobol_source") -> str:
        """Strip and validate that *source* is a non-empty string.

        Raises
        ------
        ValueError
            If *source* is empty or not a string.
        """
        if not isinstance(source, str):
            raise TypeError(f"{label} must be a string, got {type(source).__name__}")
        stripped = source.strip()
        if not stripped:
            raise ValueError(f"{label} must not be empty")
        return stripped

    @staticmethod
    def validate_context(context: dict[str, Any] | None) -> dict[str, Any]:
        """Normalise *context* to a dict (default ``{}``)."""
        if context is None:
            return {}
        if not isinstance(context, dict):
            raise TypeError(f"context must be a dict, got {type(context).__name__}")
        return context
