"""
agents — Modular multi-agent system for COBOL-to-Python migration.

This package exposes the core components:
  - Router: classifies task complexity and determines routing
  - StructureExpert: parses COBOL structure into a logical map
  - TranslationExpert: converts COBOL logic to Python code
  - DebugExpert: diagnoses and fixes errors in generated Python
  - TestExpert: generates pytest-style test cases
  - AgentController: orchestrates the full pipeline
"""

from agents.router import Router
from agents.structure_expert import StructureExpert
from agents.translation_expert import TranslationExpert
from agents.debug_expert import DebugExpert
from agents.test_expert import TestExpert
from agents.agent_controller import AgentController

__all__ = [
    "Router",
    "StructureExpert",
    "TranslationExpert",
    "DebugExpert",
    "TestExpert",
    "AgentController",
]
