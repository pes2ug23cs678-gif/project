"""Unit tests for execution layer: SandboxExecutor and Validator.

Run with:
    python -m pytest execution/test_execution.py -v
"""

import unittest
import os
import sys

# Ensure the parent directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from execution.executor import SandboxExecutor
from execution.validator import Validator


class TestSandboxExecutor(unittest.TestCase):
    """Tests for the legacy SandboxExecutor class."""

    def setUp(self):
        self.executor = SandboxExecutor(timeout_seconds=2)

    def test_successful_execution(self):
        code = "print('Hello World')"
        result = self.executor.execute(code)
        self.assertEqual(result['return_code'], 0)
        self.assertIn("Hello World", result['stdout'])
        self.assertIsNone(result['error_type'])

    def test_mock_inputs_execution(self):
        code = "import os; print(os.environ.get('MOCK_DB2_RES', 'FAILED'))"
        mock_input = {"MOCK_DB2_RES": "SUCCESS"}
        result = self.executor.execute(code, mock_inputs=mock_input)
        self.assertEqual(result['return_code'], 0)
        self.assertIn("SUCCESS", result['stdout'])

    def test_timeout_execution(self):
        code = "import time; time.sleep(5)"
        result = self.executor.execute(code)
        self.assertTrue(result['timeout'])
        self.assertEqual(result['error_type'], "TimeoutError")

    def test_runtime_error(self):
        code = "raise ValueError('Intentional Error')"
        result = self.executor.execute(code)
        self.assertNotEqual(result['return_code'], 0)
        self.assertEqual(result['error_type'], "RuntimeError")
        self.assertIn("Intentional Error", result['stderr'])


class TestValidator(unittest.TestCase):
    """Tests for the Validator class."""

    def setUp(self):
        self.validator = Validator()

    def test_exact_match(self):
        exec_result = {
            "stdout": "42\n",
            "stderr": "",
            "return_code": 0,
            "error_type": None,
        }
        is_success, report = self.validator.evaluate_execution(exec_result, "42")
        self.assertTrue(is_success)
        self.assertEqual(report["confidence_score"], 100.0)

    def test_behavioral_mismatch(self):
        exec_result = {
            "stdout": "24\n",
            "stderr": "",
            "return_code": 0,
            "error_type": None,
        }
        is_success, report = self.validator.evaluate_execution(exec_result, "42")
        self.assertFalse(is_success)
        self.assertEqual(report["reason"], "Behavioral Mismatch")
        self.assertEqual(report["SR_score"], 0.0)

    def test_runtime_failure_evaluation(self):
        exec_result = {
            "stdout": "",
            "stderr": "Exception occurred",
            "return_code": 1,
            "error_type": "RuntimeError",
        }
        is_success, report = self.validator.evaluate_execution(exec_result, "42")
        self.assertFalse(is_success)
        self.assertEqual(report["reason"], "RuntimeError")


if __name__ == '__main__':
    unittest.main()
