"""
test_expert.py — Test generation expert.

Derives test dimensions from COBOL paragraphs and data items, generates
pytest-style test stubs covering:
  • Normal / happy-path cases
  • Boundary conditions (PIC-based min/max values)
  • Error / edge cases
  • Data-type consistency checks

The output includes:
  • test_cases: human-readable list of test scenarios
  • test_code: runnable pytest skeleton
  • prompt_payload: LLM prompt to fill in assertions and values
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestCase:
    """A single test scenario."""

    name: str
    category: str          # "happy_path" | "boundary" | "error" | "type_check"
    target_function: str
    description: str
    inputs: dict[str, Any] = field(default_factory=dict)
    expected: str = "# LLM to fill expected output"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "target_function": self.target_function,
            "description": self.description,
            "inputs": self.inputs,
            "expected": self.expected,
        }


@dataclass
class TestResult:
    """Structured output from the TestExpert."""

    test_cases: list[TestCase] = field(default_factory=list)
    test_code: str = ""
    prompt_payload: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_cases": [tc.to_dict() for tc in self.test_cases],
            "test_code": self.test_code,
            "prompt_payload": self.prompt_payload,
        }


class TestExpert:
    """Generates pytest-style test cases from translated Python code."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        python_code: str,
        cobol_source: str = "",
        structure_analysis: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate test cases and a test file.

        Parameters
        ----------
        python_code : str
            Generated Python translation to test.
        cobol_source : str, optional
            Original COBOL source for cross-reference.
        structure_analysis : dict, optional
            Output of ``StructureExpert.run()`` — used to derive
            function names and data-item constraints.
        context : dict, optional
            RAG-retrieved context.

        Returns
        -------
        dict
            Keys: test_cases, test_code, prompt_payload.
        """
        structure_analysis = structure_analysis or {}
        context = context or {}
        result = TestResult()

        # Derive test cases from structure + code analysis
        result.test_cases = self._derive_test_cases(
            python_code, structure_analysis,
        )

        # Generate the pytest file
        result.test_code = self._generate_test_code(
            result.test_cases, structure_analysis,
        )

        # Build the LLM prompt
        result.prompt_payload = self._build_prompt(
            python_code, cobol_source, result, context,
        )

        return result.to_dict()

    # ------------------------------------------------------------------
    # Test case derivation
    # ------------------------------------------------------------------

    def _derive_test_cases(
        self,
        python_code: str,
        analysis: dict[str, Any],
    ) -> list[TestCase]:
        """Build a list of test scenarios from code + structural data."""
        cases: list[TestCase] = []

        # 1. Happy-path cases for each paragraph / function
        paragraphs = analysis.get("paragraphs", [])
        functions = self._extract_functions(python_code)
        targets = [p.lower().replace("-", "_") for p in paragraphs] or functions

        for fn in targets:
            cases.append(TestCase(
                name=f"test_{fn}_happy_path",
                category="happy_path",
                target_function=fn,
                description=f"Verify {fn}() produces correct output under normal conditions.",
            ))

        # 2. Boundary cases from data items
        data_items = analysis.get("data_items", [])
        for item in data_items:
            pic = item.get("picture", "")
            if not pic:
                continue
            var = item["name"].lower().replace("-", "_")
            bounds = self._pic_bounds(pic)
            if bounds:
                cases.append(TestCase(
                    name=f"test_{var}_min_boundary",
                    category="boundary",
                    target_function="main",
                    description=f"Test {var} at minimum value ({bounds['min']}).",
                    inputs={var: bounds["min"]},
                ))
                cases.append(TestCase(
                    name=f"test_{var}_max_boundary",
                    category="boundary",
                    target_function="main",
                    description=f"Test {var} at maximum value ({bounds['max']}).",
                    inputs={var: bounds["max"]},
                ))

        # 3. Type-check cases for data items
        for item in data_items:
            var = item["name"].lower().replace("-", "_")
            cases.append(TestCase(
                name=f"test_{var}_type",
                category="type_check",
                target_function="main",
                description=f"Verify {var} retains correct type after processing.",
            ))

        # 4. Error case — main with invalid input
        cases.append(TestCase(
            name="test_main_error_handling",
            category="error",
            target_function="main",
            description="Verify graceful handling of invalid or missing input.",
        ))

        return cases

    # ------------------------------------------------------------------
    # Test code generation
    # ------------------------------------------------------------------

    def _generate_test_code(
        self,
        cases: list[TestCase],
        analysis: dict[str, Any],
    ) -> str:
        """Produce a runnable pytest file from the test cases."""
        program_id = analysis.get("program_id", "program").lower().replace("-", "_")
        module_name = program_id

        lines: list[str] = [
            '"""',
            f"Auto-generated test suite for {module_name}.",
            "",
            "Run with:  pytest {0} -v".format(f"test_{module_name}.py"),
            '"""',
            "",
            "import pytest",
            f"# from {module_name} import *  # Uncomment when module is available",
            "",
            "",
        ]

        for tc in cases:
            lines.append(f"class Test{self._to_class_name(tc.target_function)}:")
            lines.append(f'    """Tests for {tc.target_function}()."""')
            lines.append("")
            lines.append(f"    def {tc.name}(self):")
            lines.append(f'        """{tc.description}"""')
            if tc.inputs:
                for var, val in tc.inputs.items():
                    lines.append(f"        {var} = {val!r}")
            lines.append(f"        # Category: {tc.category}")
            lines.append(f"        # {tc.expected}")
            lines.append("        pass  # LLM will fill assertions")
            lines.append("")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        python_code: str,
        cobol_source: str,
        result: TestResult,
        context: dict[str, Any],
    ) -> str:
        """Assemble the structured test-generation prompt."""
        case_summary = "\n".join(
            f"  - [{tc.category}] {tc.name}: {tc.description}"
            for tc in result.test_cases
        )

        cobol_section = ""
        if cobol_source.strip():
            cobol_section = f"""
## Original COBOL Source (reference)
```cobol
{cobol_source.strip()}
```
"""
        rag_section = ""
        if context:
            rag_section = (
                "\n## Retrieved Context (RAG)\n"
                + "\n".join(f"- {k}: {v}" for k, v in context.items())
            )

        return f"""\
You are a Python test-generation expert for COBOL-to-Python migrations.

## Task
Complete the pytest test suite below so every test has meaningful
assertions that verify correctness of the translated Python code.

## Python Code Under Test
```python
{python_code.strip()}
```
{cobol_section}
## Test Scenarios
{case_summary}

## Test Skeleton
```python
{result.test_code}
```
{rag_section}

## Instructions
1. Replace every `pass` with concrete assertions (assert, pytest.raises, etc.).
2. For boundary tests, use the min/max values shown in the inputs.
3. For type checks, use `isinstance()`.
4. For error tests, use `pytest.raises(...)` with the expected exception.
5. Derive expected values from the COBOL source logic.
6. Return the complete test file, no explanations.
"""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_functions(code: str) -> list[str]:
        """Extract top-level function names from Python source."""
        return re.findall(r"^def\s+(\w+)\s*\(", code, re.MULTILINE)

    @staticmethod
    def _pic_bounds(pic: str) -> dict[str, Any] | None:
        """Derive min/max numeric bounds from a PIC clause."""
        upper = pic.upper()
        # Match PIC 9(n) or PIC 9(n)V9(m)
        int_match = re.search(r"9\((\d+)\)", upper)
        if not int_match:
            nines = upper.count("9")
            if nines == 0:
                return None
            return {"min": 0, "max": int("9" * nines)}
        digits = int(int_match.group(1))
        return {"min": 0, "max": int("9" * digits)}

    @staticmethod
    def _to_class_name(fn_name: str) -> str:
        """Convert a snake_case function name to PascalCase."""
        return "".join(part.capitalize() for part in fn_name.split("_"))


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sample_code = """\
import sys
from decimal import Decimal

ws_salary: Decimal = Decimal("0")
ws_tax: Decimal = Decimal("0")

def calculate_tax():
    global ws_salary, ws_tax
    ws_tax = ws_salary * Decimal("0.30")

def print_result():
    print(f"Tax: {ws_tax}")

def main():
    calculate_tax()
    print_result()

if __name__ == "__main__":
    main()
"""

    sample_analysis = {
        "program_id": "PAYROLL",
        "paragraphs": ["CALCULATE-TAX", "PRINT-RESULT"],
        "data_items": [
            {"name": "WS-SALARY", "picture": "9(7)V99", "value": ""},
            {"name": "WS-TAX", "picture": "9(7)V99", "value": ""},
        ],
    }

    expert = TestExpert()
    result = expert.run(sample_code, structure_analysis=sample_analysis)
    print("=== Test Cases ===")
    for tc in result["test_cases"]:
        print(f"  [{tc['category']}] {tc['name']}: {tc['description']}")
    print("\n=== Test Code (first 600 chars) ===")
    print(result["test_code"][:600])
