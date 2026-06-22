"""Automated pytest test-case generation expert."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from agents.base import BaseExpert
from agents.prompts import TestPrompt
from config import GROQ_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, OPENAI_MAX_TOKENS

# Shared LLM client (same backend as TranslationExpert)
_client = OpenAI(api_key=GROQ_API_KEY, base_url=OPENAI_BASE_URL)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    """A single test scenario."""

    name: str
    category: str   # "happy_path" | "boundary" | "error" | "type_check"
    target_function: str
    description: str
    inputs: dict[str, Any] = field(default_factory=dict)
    expected: str = "# LLM to fill expected output"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "category": self.category,
            "target_function": self.target_function,
            "description": self.description,
            "inputs": self.inputs, "expected": self.expected,
        }


@dataclass
class TestResult:
    test_cases: list[TestCase] = field(default_factory=list)
    test_code: str = ""
    prompt_payload: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_cases": [tc.to_dict() for tc in self.test_cases],
            "test_code": self.test_code,
            "prompt_payload": self.prompt_payload,
        }


# ---------------------------------------------------------------------------
# Expert
# ---------------------------------------------------------------------------

class TestExpert(BaseExpert):
    """Generates pytest-style test cases from translated Python code."""

    def run(
        self,
        python_code: str = "",
        cobol_source: str = "",
        structure_analysis: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        """Generate test cases and a fully-asserted test file via LLM."""
        ctx = self.validate_context(context)
        analysis = structure_analysis or {}
        result = TestResult()

        # 1. Derive structured test-case metadata (fast, rule-based)
        result.test_cases = self._derive_cases(python_code, analysis)

        # 2. Build the pytest skeleton (stubs with pass)
        skeleton = self._gen_code(result.test_cases, analysis)

        # 3. Build the LLM prompt
        case_summary = "\n".join(
            f"  - [{tc.category}] {tc.name}: {tc.description}"
            for tc in result.test_cases
        )
        result.prompt_payload = TestPrompt.build(
            python_code=python_code, cobol_source=cobol_source,
            test_cases_summary=case_summary, test_skeleton=skeleton,
            context=ctx,
        )

        # 4. Call Groq to fill assertions (falls back to skeleton on error)
        result.test_code = self._call_llm(result.prompt_payload, skeleton)

        self.logger.debug("Generated %d test cases", len(result.test_cases))
        return result.to_dict()

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, fallback: str) -> str:
        """Ask Groq to fill in pytest assertions. Returns fallback on failure."""
        try:
            response = _client.chat.completions.create(
                model=OPENAI_MODEL,
                max_tokens=OPENAI_MAX_TOKENS,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior QA engineer. Complete the pytest file "
                            "below so every `pass` stub is replaced with meaningful "
                            "assertions. Return ONLY the complete Python file — "
                            "no markdown fences, no explanations."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            raw = response.choices[0].message.content.strip()
            return self._strip_markdown(raw) or fallback
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("LLM call failed, using skeleton: %s", exc)
            return fallback

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Remove ```python … ``` fences if the LLM wraps its output."""
        m = re.match(r'^```(?:python)?\s*\n(.*?)```\s*$', text, re.DOTALL)
        if m:
            return m.group(1).strip()
        if text.startswith("```"):
            lines = text.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return text

    # ------------------------------------------------------------------
    # Test case derivation
    # ------------------------------------------------------------------

    def _derive_cases(
        self, code: str, analysis: dict[str, Any],
    ) -> list[TestCase]:
        cases: list[TestCase] = []
        paragraphs = analysis.get("paragraphs", [])
        functions = self._extract_functions(code)
        targets = [p.lower().replace("-", "_") for p in paragraphs] or functions

        # Happy-path per function
        for fn in targets:
            cases.append(TestCase(
                name=f"test_{fn}_happy_path", category="happy_path",
                target_function=fn,
                description=f"Verify {fn}() under normal conditions.",
            ))

        # Boundary cases from data items
        for item in analysis.get("data_items", []):
            pic = item.get("picture", "")
            if not pic:
                continue
            var = item["name"].lower().replace("-", "_")
            bounds = self._pic_bounds(pic)
            if bounds:
                cases.append(TestCase(
                    name=f"test_{var}_min", category="boundary",
                    target_function="main",
                    description=f"{var} at minimum ({bounds['min']}).",
                    inputs={var: bounds["min"]},
                ))
                cases.append(TestCase(
                    name=f"test_{var}_max", category="boundary",
                    target_function="main",
                    description=f"{var} at maximum ({bounds['max']}).",
                    inputs={var: bounds["max"]},
                ))

        # Type checks
        for item in analysis.get("data_items", []):
            var = item["name"].lower().replace("-", "_")
            cases.append(TestCase(
                name=f"test_{var}_type", category="type_check",
                target_function="main",
                description=f"Verify {var} type after processing.",
            ))

        # Error case
        cases.append(TestCase(
            name="test_main_error_handling", category="error",
            target_function="main",
            description="Verify graceful error handling.",
        ))
        return cases

    # ------------------------------------------------------------------
    # Test code generation
    # ------------------------------------------------------------------

    def _gen_code(
        self, cases: list[TestCase], analysis: dict[str, Any],
    ) -> str:
        module = analysis.get("program_id", "program").lower().replace("-", "_")
        lines: list[str] = [
            '"""', f"Auto-generated test suite for {module}.",
            "", f"Run with:  pytest test_{module}.py -v", '"""',
            "", "import pytest",
            f"import {module}",
            "", "",
        ]
        for tc in cases:
            cls = "".join(p.capitalize() for p in tc.target_function.split("_"))
            lines += [
                f"class Test{cls}:",
                f'    """Tests for {tc.target_function}()."""', "",
                f"    def {tc.name}(self):",
                f'        """{tc.description}"""',
            ]
            for var, val in tc.inputs.items():
                lines.append(f"        {var} = {val!r}")
            lines += [
                f"        # Category: {tc.category}",
                f"        # {tc.expected}",
                "        pass  # LLM will fill assertions", "", "",
            ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_functions(code: str) -> list[str]:
        return re.findall(r"^def\s+(\w+)\s*\(", code, re.MULTILINE)

    @staticmethod
    def _pic_bounds(pic: str) -> dict[str, Any] | None:
        upper = pic.upper()
        m = re.search(r"9\((\d+)\)", upper)
        digits = int(m.group(1)) if m else upper.count("9")
        return {"min": 0, "max": int("9" * digits)} if digits else None
