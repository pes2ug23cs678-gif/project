"""COBOL-to-Python multi-agent migration system.

Public API (new model stack):
    from agents.router import classify
    from agents.translation_expert import generate_python
    from agents.debug_expert import fix_code
"""

__version__ = "2.0.0"

__all__ = [
    "classify",
    "generate_python",
    "fix_code",
]
