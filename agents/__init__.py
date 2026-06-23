"""COBOL-to-Python multi-agent migration system.

Public API (new model stack):
    from agents.router import classify
    from agents.translation_expert import generate_python
    from agents.debug_expert import fix_code
    from agents.agent_controller import AgentController
"""

from agents.agent_controller import AgentController

__version__ = "2.0.0"

__all__ = [
    "AgentController",
    "classify",
    "generate_python",
    "fix_code",
]
