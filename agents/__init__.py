"""COBOL-to-Python multi-agent migration system.

Public API:

    from agents import AgentController, PipelineConfig, Complexity, Severity

    controller = AgentController()
    result = controller.run(cobol_source=src)
"""

__version__ = "1.0.0"

from config import Complexity, PipelineConfig, Severity  # noqa: F401
from agents.agent_controller import AgentController              # noqa: F401

__all__ = [
    "AgentController",
    "Complexity",
    "PipelineConfig",
    "Severity",
]
