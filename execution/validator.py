class Validator:
    """
    Validator evaluates the results of executing the translated Python code.
    It checks output equivalence with original COBOL expected outputs and calculates the Success Rate (SR).
    """

    def __init__(self):
        pass

    def evaluate_execution(self, execution_result, expected_output):
        """
        Evaluates the sandbox execution results.
        :param execution_result: Dictionary returned from SandboxExecutor.
        :param expected_output: String or Dictionary, the expected output from original COBOL execution.
        :return: A tuple (is_successful, evaluation_report)
        """
        # If there were runtime crashes or timeouts, it's an immediate failure.
        if execution_result["return_code"] != 0:
            report = {
                "success": False,
                "reason": execution_result["error_type"],
                "details": execution_result["stderr"],
                "confidence_score": 0.0
            }
            return False, report
        
        # In a real environment, we would do token-based or regex equality.
        actual_output = execution_result["stdout"].strip()
        expected = str(expected_output).strip() if expected_output else ""
        
        if actual_output == expected:
            report = {
                "success": True,
                "reason": "Exact Output Match",
                "details": f"Output perfectly matches expected COBOL output.",
                "confidence_score": 100.0,
                "SR_score": 1.0 # Success Rate (100% tests passed)
            }
            return True, report
        else:
            # Output mismatch
            report = {
                "success": False,
                "reason": "Behavioral Mismatch",
                "details": f"Actual Output:\n{actual_output}\n\nExpected:\n{expected}",
                "confidence_score": 50.0, # Semantic logic ran, but answers differ
                "SR_score": 0.0
            }
            return False, report
