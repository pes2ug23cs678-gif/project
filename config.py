"""Central configuration — all model settings in one place."""

import os

# ── LLM Backend ─────────────────────────────────────────────────────────
LLM_BACKEND = os.environ.get("LLM_BACKEND", "groq")

# Groq — OpenAI-compatible API
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")
OPENAI_BASE_URL   = os.environ.get("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
OPENAI_MODEL      = os.environ.get("OPENAI_MODEL", "llama-3.1-8b-instant")
OPENAI_MAX_TOKENS = int(os.environ.get("OPENAI_MAX_TOKENS", "4096"))

# Aliases — kept for any code that still references DEEPSEEK_* names
DEEPSEEK_API_KEY    = GROQ_API_KEY
DEEPSEEK_BASE_URL   = OPENAI_BASE_URL
DEEPSEEK_MODEL      = OPENAI_MODEL
DEEPSEEK_MAX_TOKENS = OPENAI_MAX_TOKENS

# ── SmolLM — used for routing only, runs via Ollama locally ─────────────
SMOLLM_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
SMOLLM_MODEL    = os.environ.get("SMOLLM_MODEL", "smollm:135m")

# Speed up HuggingFace sentence-transformers (prevents slow network checks for RAG)
os.environ["HF_HUB_OFFLINE"] = "1"

# ── Sandbox ─────────────────────────────────────────────────────────────
SANDBOX_TIMEOUT        = 5    # seconds — single-file execution
SANDBOX_MAX_ITER       = 5    # max debug iterations
PYTEST_SANDBOX_TIMEOUT = 30   # seconds — full pytest suite (needs more headroom)

# ── COBOL keywords — used by structure_expert to exclude paragraph labels ──
COBOL_KEYWORDS: frozenset[str] = frozenset({
    "IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE",
    "WORKING-STORAGE", "FILE-CONTROL", "INPUT-OUTPUT",
    "LINKAGE", "CONFIGURATION", "FILE",
    "FD", "SD", "COPY", "REPLACE",
    "SECTION", "DIVISION",
})


# ── Pipeline configuration ──────────────────────────────────────────────
class PipelineConfig:
    """Top-level configuration for the pipeline controller."""

    def __init__(
        self,
        max_debug_retries: int = 3,
        sandbox_timeout: int = SANDBOX_TIMEOUT,
        pytest_timeout: int = PYTEST_SANDBOX_TIMEOUT,
    ) -> None:
        self.max_debug_retries = max_debug_retries
        self.sandbox_timeout = sandbox_timeout
        self.pytest_timeout = pytest_timeout
