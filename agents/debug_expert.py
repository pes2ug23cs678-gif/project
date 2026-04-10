"""Debug Expert — uses Groq (llama-3.3-70b-versatile) via OpenAI-compatible API to fix Python code."""

import re
from openai import OpenAI
from config import GROQ_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, OPENAI_MAX_TOKENS

_client = OpenAI(api_key=GROQ_API_KEY, base_url=OPENAI_BASE_URL)

DEBUG_PROMPT = """You are a Python code repair engine.
You receive broken Python code and the error it produces.
You return the complete fixed Python file -- nothing else.
No markdown. No explanation. No preamble.
First character must be a quote or hash.
Fix only what the error requires. Do not rewrite working sections."""


def fix_code(broken_code: str, error_type: str, stderr: str, stdout: str) -> str:
    """
    Send broken code + error to Groq and return fixed code.
    Used by the debug loop for errors it cannot fix with static rules.
    """
    user_message = (
        f"ERROR TYPE: {error_type}\n"
        f"STDERR:\n{stderr[:1000]}\n"
        f"STDOUT:\n{stdout[:500]}\n\n"
        f"BROKEN CODE:\n{broken_code}"
    )

    response = _client.chat.completions.create(
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
