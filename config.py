"""Central configuration — all model settings in one place."""
import os

# LLM Backend — used for translation and debug
LLM_BACKEND       = os.environ.get("LLM_BACKEND", "groq")

# Groq — OpenAI-compatible API
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")
OPENAI_BASE_URL   = os.environ.get("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
OPENAI_MODEL      = os.environ.get("OPENAI_MODEL", "llama-3.3-70b-versatile")
OPENAI_MAX_TOKENS = 8192

# Aliases — kept for any code that still references DEEPSEEK_* names
DEEPSEEK_API_KEY    = GROQ_API_KEY
DEEPSEEK_BASE_URL   = OPENAI_BASE_URL
DEEPSEEK_MODEL      = OPENAI_MODEL
DEEPSEEK_MAX_TOKENS = OPENAI_MAX_TOKENS

# SmolLM — used for routing only, runs via Ollama locally
SMOLLM_BASE_URL   = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
SMOLLM_MODEL      = os.environ.get("SMOLLM_MODEL", "smollm:135m")

# Sandbox
SANDBOX_TIMEOUT   = 5   # seconds
SANDBOX_MAX_ITER  = 7   # max debug iterations
