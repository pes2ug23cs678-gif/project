"""Translation Expert — Expert 3. Uses Groq (llama-3.3-70b-versatile) via OpenAI-compatible API."""

import re
from openai import OpenAI
from config import GROQ_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, OPENAI_MAX_TOKENS

_client = OpenAI(api_key=GROQ_API_KEY, base_url=OPENAI_BASE_URL)

TRANSLATION_PROMPT = """
You are a COBOL-to-Python translation engine. You receive COBOL source code
and return one complete, immediately runnable Python source file.

OUTPUT FORMAT RULES — non-negotiable:
- No markdown fences. No explanation. No preamble. No postamble.
- First character must be a quote or hash.
- Last line must be    sys.exit(0)    inside the __main__ block.
- File must pass: python3 -m py_compile

FILE STRUCTURE — emit in this order:
1. Module docstring (one line)
2. Imports: sys, os, decimal — only what is used
3. File path constants — one string per SELECT/ASSIGN
4. Working-storage globals — one Python variable per COBOL field
5. File handle globals — all None
6. Helper functions: _parse_*_line(), _amount_as_char()
7. One def per COBOL paragraph
8. if __name__ == "__main__": calls main paragraph then sys.exit(0)

TRANSLATION RULES:

OPERATORS:
  COBOL = in conditions -> Python ==
  IF WS-EOF-ACC = 'Y'   ->  if ws_eof_acc == "Y":
  IF ACC-ID = ZERO       ->  if acc_id == 0:
  IF ACC-NAME = SPACES   ->  if acc_name.strip() == "":
  UNTIL X = 'Y'          ->  while x != "Y":
  Never use single = in if/elif/while. Always ==.

FIGURATIVE CONSTANTS:
  ZERO/ZEROS/ZEROES -> 0 or Decimal("0")
  SPACES/SPACE      -> "" with .strip() == "" for comparison
  Never use zero or spaces as Python variable names.

DATA TYPES:
  PIC 9(n)            -> int = 0
  PIC X(n)            -> str = ""
  PIC S9(n)V99 COMP-3 -> Decimal = Decimal("0")

OCCURS -> list of dicts:
  05 TABLE OCCURS 50 TIMES.
      10 T-ID   PIC 9(6).
      10 T-TYPE PIC X(1).
      10 T-AMT  PIC S9(7)V99 COMP-3.
  ->
  table = [{"t_id": 0, "t_type": "", "t_amt": Decimal("0")} for _ in range(50)]
  Access: table[cobol_idx - 1]["t_amt"]
  NEVER write t_amt(idx) -- that is a function call and crashes.

PERFORM VARYING -> for loop:
  PERFORM VARYING IDX FROM 1 BY 1 UNTIL IDX > 50
  ->
  for cobol_idx in range(1, 51):
      slot = cobol_idx - 1
  With OR condition:
  UNTIL IDX > 50 OR WS-EOF = 'Y'
  ->
  for cobol_idx in range(1, 51):
      if ws_eof == "Y":
          break
      slot = cobol_idx - 1
  NEVER call varying(). It does not exist.

PERFORM UNTIL -> while:
  PERFORM X UNTIL WS-EOF = 'Y'  ->  while ws_eof != "Y": x()

EVALUATE -> if/elif/else with subject:
  EVALUATE WS-TYPE
      WHEN 'D' ...
      WHEN 'W' ...
      WHEN OTHER ...
  ->
  if ws_type == "D":
      ...
  elif ws_type == "W":
      ...
  else:
      ...
  NEVER write if "D": -- a bare string is always True.

READ ... AT END -> readline with both branches implemented:
  READ FILE AT END MOVE 'Y' TO EOF NOT AT END [process]
  ->
  line = _file_fh.readline()
  if not line:
      ws_eof = "Y"
  else:
      rec = _parse_line(line)
      field = rec["field"]
  NEVER leave AT END as a comment.

WRITE -> file.write() -- NEVER leave as comment:
  WRITE REPORT-REC  ->  _report_fh.write(report_rec.ljust(120) + "\\n")

STRING DELIMITED BY SIZE -> string concat -- NEVER leave as comment:
  STRING "ID:" ACC-ID " NAME:" ACC-NAME DELIMITED BY SIZE INTO REPORT-REC
  ->
  report_rec = ("ID:" + str(acc_id).zfill(6) + " NAME:" + acc_name[:25].ljust(25))[:120]

MOVE:
  MOVE 'Y' TO WS-EOF     ->  ws_eof = "Y"
  MOVE SPACES TO REC     ->  rec = ""
  MOVE X TO TABLE(IDX)   ->  table[slot]["field"] = x

ADD/SUBTRACT/COMPUTE:
  ADD X TO Y        ->  y += x
  SUBTRACT X FROM Y ->  y -= x
  ADD 1 TO ERRORS   ->  ws_tot_errors += 1

GO TO paragraph:
  GO TO INVALID-TRANS  ->  invalid_trans(); return

REDEFINES -> helper function:
  05 WS-AMOUNT-NUM  PIC 9(9)V99.
  05 WS-AMOUNT-CHAR REDEFINES WS-AMOUNT-NUM PIC X(11).
  ->
  def _amount_as_char(value: Decimal) -> str:
      sign = "-" if value < 0 else " "
      return f"{sign}{abs(value):010.2f}"[:11]
  NEVER write ws_amount_char = ws_amount_num.

FILE HANDLES:
  Declare all as None at module level.
  Open in init() with try/except IOError -- on failure set EOF flag, never crash.
  Close all in cleanup().
  Paths are always string constants, never integers.
  ACCOUNT_FILE_PATH = "accounts.dat"  <- correct
  account_file_path = 0               <- NEVER, crashes open()

FIXED-WIDTH PARSING -- use slicing, never split():
  PIC 9(n)     -> int(line[s:e].strip() or "0")
  PIC X(n)     -> line[s:e]
  PIC S9(n)V99 -> Decimal(raw) if "." in raw else Decimal(raw) / 100

FIELD WIDTH CALCULATION -- most common source of parser bugs:
  PIC 9(n)     = exactly n characters
  PIC X(n)     = exactly n characters
  PIC 9(n)V99  = n + 2 characters  (V adds implied decimal digits)
  PIC 9(n)V999 = n + 3 characters

  Always sum field widths cumulatively for slice positions:
    PIC 9(5)      width=5,  slice [0:5]
    PIC X(1)      width=1,  slice [5:6]
    PIC 9(5)V99   width=7,  slice [6:13]   <- 5+2=7, NOT 6
    PIC 9(7)V99   width=9,  slice [0:9]    <- 7+2=9, NOT 8

GLOBAL STATE:
  Every function mutating module-level variables must declare them:
  def apply_transactions() -> None:
      global acc_balance, ws_tot_deposit, ws_tot_withdraw, ws_tot_errors
  Never omit global -- Python silently creates a local instead.

STOP RUN:
  Never call sys.exit() inside paragraph functions.
  Only in: if __name__ == "__main__":

SANDBOX RULES:
  File path constants must be string literals at module level.
  All file opens inside try/except IOError in init().
  Program must exit 0 even when all input files are empty.

INIT PARAGRAPH -- READ priming rule:
  When init() reads the first record it must BOTH check for EOF
  AND parse+store the record into the current record variable.
  Never discard the first line. Pattern:
    line = _emp_fh.readline()
    if not line:
        ws_eof_emp = "Y"
    else:
        emp_rec = _parse_emp_line(line)   # always store it

MAIN LOOP -- never re-read a line that init() already read:
  Declare all record variables at module level with default values.
  The main loop must NOT call readline() again before processing
  the record that init() already stored:
    # correct pattern:
    while ws_eof_emp != "Y":
        process_employees()   # process_employees reads the NEXT line internally
  process_employees() must:
    1. use the current emp_rec (already stored by init or previous iteration)
    2. then call read_employee() to prime the NEXT iteration
  Never put a global declaration inside a while or for loop body.

PRE-EMIT CHECKLIST -- fix any False before outputting:
  [ ] No varying() call
  [ ] No field(idx) function-call syntax on list items
  [ ] No bare if "VALUE": in conditions
  [ ] No zero/spaces as identifiers
  [ ] No file path = integer
  [ ] No STRING left as comment
  [ ] No AT END left as comment
  [ ] No sys.exit() in paragraph functions
  [ ] Every mutating function has global declaration
  [ ] All file handles = None at module level
  [ ] Fixed-width parsers use slicing
  [ ] __main__ block is last
  [ ] Exits 0 on empty input files
"""


def _strip_markdown(text: str) -> str:
    text = text.strip()
    match = re.match(r'^```(?:python)?\s*\n(.*?)```\s*$', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def generate_python(cobol_code: str, structured_analysis: dict = None) -> str:
    """Translate any COBOL program to Python using Groq (llama-3.3-70b-versatile)."""
    user_message = cobol_code.strip()

    if structured_analysis:
        program_id = structured_analysis.get("program_id", "UNKNOWN")
        complexity = structured_analysis.get("complexity", "unknown")
        paragraphs = structured_analysis.get("paragraphs", [])
        para_list  = ", ".join(paragraphs) if isinstance(paragraphs, list) else str(paragraphs)
        user_message = (
            f"Program: {program_id}\n"
            f"Complexity: {complexity}\n"
            f"Paragraphs: {para_list}\n\n"
            f"{cobol_code.strip()}"
        )

    response = _client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=OPENAI_MAX_TOKENS,
        temperature=0,
        messages=[
            {"role": "system", "content": TRANSLATION_PROMPT},
            {"role": "user",   "content": user_message}
        ]
    )

    raw = response.choices[0].message.content
    return _strip_markdown(raw).strip()
