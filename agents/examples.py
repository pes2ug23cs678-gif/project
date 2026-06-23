"""Runnable examples for the agents package.

Usage:
    python -m agents.examples
"""

from __future__ import annotations

import logging

from agents.agent_controller import AgentController


SAMPLE_COBOL = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYROLL.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT EMPLOYEE-FILE ASSIGN TO 'EMP.DAT'.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SALARY PIC 9(7)V99.
       01 WS-TAX    PIC 9(7)V99.
       01 WS-ACTIVE PIC X.
          88 IS-ACTIVE   VALUE 'Y'.
          88 IS-INACTIVE VALUE 'N'.
       PROCEDURE DIVISION.
       MAIN-LOGIC.
           PERFORM CALCULATE-TAX.
           PERFORM PRINT-RESULT.
           STOP RUN.
       CALCULATE-TAX.
           COMPUTE WS-TAX = WS-SALARY * 0.30.
       PRINT-RESULT.
           DISPLAY 'Tax: ' WS-TAX.
"""


def run_normal_pipeline() -> None:
    """Demonstrate the standard translation pipeline."""
    print("=" * 60)
    print("  NORMAL PIPELINE RUN")
    print("=" * 60)

    controller = AgentController()
    result = controller.run(cobol_source=SAMPLE_COBOL)

    routing = result.get("routing", {})
    print(f"\nRouting     : {routing.get('complexity', 'N/A')}")
    print(f"Structure   : {result.get('structure', {}).get('program_id', 'N/A')}")
    print(f"Translation : {len(result.get('translation', {}).get('python_code', ''))} chars")
    print(f"Tests       : {len(result.get('tests', {}).get('test_cases', []))} cases")
    print(f"Iterations  : {result.get('iterations', 0)}")

    code = result.get("translation", {}).get("python_code", "")
    if code:
        print("\n--- Generated Python ---")
        print(code)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)-5s | %(name)s | %(message)s",
    )
    run_normal_pipeline()
