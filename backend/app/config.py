import os
from pathlib import Path

# Paths
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent

DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_DIR / "data"))
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "foods.db"))
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", PROJECT_DIR / "frontend"))

# ==============================================================================
# LLM Provider Configuration
# Set USE_LOCAL_LLM=true to use local Ollama on host, or false for external API
# ==============================================================================
USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "false").strip().lower() in ("true", "1", "yes")

# --- Local Ollama configuration (active when USE_LOCAL_LLM=true) ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2").strip()
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "30.0"))

# --- External LLM configuration (active when USE_LOCAL_LLM=false) ---
# Supports any external LLM: Gemini, OpenAI, Groq, DeepSeek, Mistral, OpenRouter, etc.
EXTERNAL_API_KEY = (
    os.getenv("EXTERNAL_API_KEY")
    or os.getenv("LLM_API_KEY")
    or os.getenv("GEMINI_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or ""
).strip()

EXTERNAL_MODEL = (
    os.getenv("EXTERNAL_MODEL")
    or os.getenv("LLM_MODEL")
    or os.getenv("GEMINI_MODEL")
    or os.getenv("OPENAI_MODEL")
    or "gemini-3.8-flash"
).strip()

EXTERNAL_BASE_URL = (
    os.getenv("EXTERNAL_BASE_URL")
    or os.getenv("LLM_BASE_URL")
    or ""
).strip()

EXTERNAL_TIMEOUT = float(
    os.getenv("EXTERNAL_TIMEOUT")
    or os.getenv("LLM_TIMEOUT")
    or os.getenv("GEMINI_TIMEOUT")
    or "25.0"
)

# Backwards compatibility aliases
GEMINI_API_KEY = EXTERNAL_API_KEY
GEMINI_MODEL = EXTERNAL_MODEL
GEMINI_TIMEOUT = EXTERNAL_TIMEOUT
