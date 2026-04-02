from .executor import SandboxExecutor
from .validator import Validator

class DebugLoop:
    """
    Orchestrates the Execution, Validation, and Feedback loop.
    Iteratively runs code, validates it, and generates Fault Localization Prompts for Srujan's agents.
    """
    
    def __init__(self, max_retries=3):
        self.max_retries = max_retries
        self.executor = SandboxExecutor()
        self.validator = Validator()

    def generate_fault_localization_prompt(self, code_string, eval_report):
        """
        Creates a structured prompt intended for the SLM Router / Debug Expert.
        It uses the strategy from the "Automated Testing of COBOL to Java Transformation" paper.
        """
        prompt = f"""
[FAULT LOCALIZATION FEEDBACK]
The generated Python code failed validation.

Target Code Attempted:
```python
{code_string}
```

Validation Error Type: {eval_report['reason']}
Error Details:
{eval_report['details']}

Please review the path of execution. Ensure that logic (like loop inversions or mocked DB queries) matches COBOL semantics.
Provide the corrected complete python string.
"""
        return prompt.strip()

    def run_with_feedback(self, initial_code, expected_output, mock_inputs, agent_callback):
        """
        The main reliability layer loop.
        :param initial_code: The first draft python code string from translation agents.
        :param expected_output: What the code is supposed to output.
        :param mock_inputs: Mock environment variables setup for this specific test case.
        :param agent_callback: A function/callback to Srujan's SLM agent that takes a prompt and returns new code.
        :return: (Final Code String, is_success)
        """
        current_code = initial_code
        
        for attempt in range(1, self.max_retries + 1):
            print(f"[DebugLoop] Attempt {attempt}/{self.max_retries}...")
            
            # Step 1: Sandbox Execution
            exec_result = self.executor.execute(current_code, mock_inputs=mock_inputs)
            
            # Step 2: Validation Gate
            is_success, eval_report = self.validator.evaluate_execution(exec_result, expected_output)
            
            if is_success:
                print("[DebugLoop] Validation Passed! 100% test pass confidence.")
                return current_code, True
                
            # Step 3: Self-Debugging (Feedback)
            print(f"[DebugLoop] Validation Failed on attempt {attempt}. Generating feedback...")
            fault_prompt = self.generate_fault_localization_prompt(current_code, eval_report)
            
            if attempt < self.max_retries:
                # Call Srujan's MoE agent here using the callback
                current_code = agent_callback(fault_prompt)
            else:
                print("[DebugLoop] Max retries reached. Validation Gate failed.")
                
        return current_code, False
