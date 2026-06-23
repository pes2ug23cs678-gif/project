"""Debug Expert — uses Groq (llama-3.3-70b-versatile) via OpenAI-compatible API to fix Python code."""

import re
from openai import OpenAI
from agents.retry import call_with_retry

_client = None


def _get_client() -> OpenAI:
    """Lazy-init the OpenAI client so .env is loaded before we read the key."""
    global _client
    if _client is None:
        from config import GROQ_API_KEY, OPENAI_BASE_URL
        _client = OpenAI(api_key=GROQ_API_KEY, base_url=OPENAI_BASE_URL)
    return _client

DEBUG_PROMPT = """\
You are a Python code repair engine specialising in COBOL-to-Python migration output.

You receive broken Python code and the error it produces.
You return the COMPLETE fixed Python file — nothing else.

CRITICAL RULES — non-negotiable:
- No markdown fences. No explanation. No preamble.
- First character must be a quote, hash, or 'import'/'from'.
- Return the ENTIRE file, not just the changed lines.
- Fix only what the error requires. Do not rewrite working sections.
- Preserve all existing function names and global declarations.

COMMON FIX PATTERNS:
- NameError for a global → add 'global varname' at top of the function.
- FileNotFoundError → wrap open() in try/except and set EOF flag on failure.
- TypeError on Decimal → use Decimal(str(value)), not Decimal(float).
- IndentationError → fix whitespace; use 4-space indent throughout.
- ValueError on int() → use int(string.strip() or "0") for safe parsing.
- IndexError on slicing → check line length before fixed-width slicing.
- 'varying()' NameError → remove the call entirely (it's a translation artifact).
- If code runs but tests fail on assertion → the TEST may be wrong; fix only
  obvious code bugs, do NOT invent new logic.

DO NOT:
- Add new imports not needed for the fix.
- Rename functions or variables.
- Remove 'global' declarations.
- Change file path string constants to integers.
- Use exec() or eval().
- Wrap entire program in try/except.
- Call sys.exit() inside paragraph functions — only in __main__ block."""


def fix_code(broken_code: str, error_type: str, stderr: str, stdout: str) -> str:
    """
    Send broken code + error to Groq and return fixed code.
    Used by the debug loop for errors it cannot fix with static rules.
    """
    from config import OPENAI_MODEL, OPENAI_MAX_TOKENS
    client = _get_client()

    # Truncate intelligently — keep the most useful parts of error output
    stderr_truncated = stderr[:3000] if stderr else ""
    stdout_truncated = stdout[:1000] if stdout else ""

    user_message = (
        f"ERROR TYPE: {error_type}\n"
        f"STDERR / PYTEST REPORT:\n{stderr_truncated}\n"
        f"STDOUT:\n{stdout_truncated}\n\n"
        f"BROKEN CODE:\n{broken_code}"
    )

    response = call_with_retry(
        client.chat.completions.create,
        model=OPENAI_MODEL,
        max_tokens=OPENAI_MAX_TOKENS,
        temperature=0,
        messages=[
            {"role": "system", "content": DEBUG_PROMPT},
            {"role": "user",   "content": user_message}
        ]
    )

    raw = response.choices[0].message.content
    return _strip_markdown(raw).strip()


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
