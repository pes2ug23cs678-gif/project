"""Runnable examples for the agents package.

Usage:
    python -m agents.examples
"""

from __future__ import annotations

import logging

from agents import AgentController


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

    print(f"\nRouting     : {result['routing']['complexity']} "
          f"(score {result['routing']['score']})")
    print(f"Structure   : {result['structure'].get('program_id', 'N/A')}")
    print(f"Translation : {len(result['translation'].get('python_code', ''))} chars")
    print(f"Tests       : {len(result['tests'].get('test_cases', []))} cases")
    print(f"Iterations  : {result['iterations']}")

    print("\n--- Generated Python ---")
    print(result["translation"]["python_code"])


def run_debug_pipeline() -> None:
    """Demonstrate the debug-loop pipeline."""
    print("\n" + "=" * 60)
    print("  DEBUG PIPELINE RUN")
    print("=" * 60)

    error = (
        "Traceback (most recent call last):\n"
        '  File "payroll.py", line 17, in main\n'
        "    calculate_tax()\n"
        '  File "payroll.py", line 8, in calculate_tax\n'
        '    ws_tax = ws_salry * Decimal("0.30")\n'
        "NameError: name 'ws_salry' is not defined. "
        "Did you mean: 'ws_salary'?"
    )

    controller = AgentController()
    result = controller.run(cobol_source=SAMPLE_COBOL, error_message=error)

    print(f"\nDebug history: {len(result['debug_history'])} entries")
    for entry in result["debug_history"]:
        print(f"  iter {entry.get('iteration')}: "
              f"{entry.get('error_type', 'N/A')} "
              f"(severity {entry.get('severity', '?')}/5) — "
              f"{entry.get('error_summary', 'N/A')}")
    print(f"Iterations  : {result['iterations']}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)-5s | %(name)s | %(message)s",
    )
    run_normal_pipeline()
    run_debug_pipeline()
