import unittest
import os
import sys

# Ensure the parent directory is in sys.path so we can import execution modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from execution.executor import SandboxExecutor
from execution.validator import Validator
from execution.debug_loop import DebugLoop

class TestSandboxExecutor(unittest.TestCase):
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
    def setUp(self):
        self.validator = Validator()

    def test_exact_match(self):
        exec_result = {
            "stdout": "42\n",
            "stderr": "",
            "return_code": 0,
            "error_type": None
        }
        is_success, report = self.validator.evaluate_execution(exec_result, "42")
        self.assertTrue(is_success)
        self.assertEqual(report["confidence_score"], 100.0)

    def test_behavioral_mismatch(self):
        exec_result = {
            "stdout": "24\n",
            "stderr": "",
            "return_code": 0,
            "error_type": None
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
            "error_type": "RuntimeError"
        }
        is_success, report = self.validator.evaluate_execution(exec_result, "42")
        self.assertFalse(is_success)
        self.assertEqual(report["reason"], "RuntimeError")

class TestDebugLoop(unittest.TestCase):
    def setUp(self):
        self.loop = DebugLoop(max_retries=2)
        
    def test_generate_prompt(self):
        code = "print(0)"
        report = {"reason": "Behavioral Mismatch", "details": "Expected 1"}
        prompt = self.loop.generate_fault_localization_prompt(code, report)
        self.assertIn("```python", prompt)
        self.assertIn("print(0)", prompt)
        self.assertIn("Behavioral Mismatch", prompt)

    def test_run_with_feedback_success_first_try(self):
        # The mock agent won't even be called if it's successful initially
        code = "print('OK')"
        def mock_agent(prompt):
            raise AssertionError("Should not be called")
        
        final_code, is_success = self.loop.run_with_feedback(code, "OK", None, mock_agent)
        self.assertTrue(is_success)
        self.assertEqual(final_code, code)

    def test_run_with_feedback_eventual_success(self):
        # Fails first, mock agent fixes it
        code_v1 = "print('FAIL')"
        code_v2 = "print('OK')"
        
        agent_call_count = [0]
        def mock_agent(prompt):
            agent_call_count[0] += 1
            return code_v2
            
        final_code, is_success = self.loop.run_with_feedback(code_v1, "OK", None, mock_agent)
        self.assertTrue(is_success)
        self.assertEqual(final_code, code_v2)
        self.assertEqual(agent_call_count[0], 1)

    def test_run_with_feedback_max_retries_failure(self):
        # Even the mock agent can't fix it
        code_bad = "print('FAIL')"
        def mock_agent(prompt):
            return "print('STILL FAIL')"
            
        final_code, is_success = self.loop.run_with_feedback(code_bad, "OK", None, mock_agent)
        self.assertFalse(is_success)
        self.assertEqual(final_code, "print('STILL FAIL')")

if __name__ == '__main__':
    unittest.main()
