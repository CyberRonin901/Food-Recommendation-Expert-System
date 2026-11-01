import os
from pathlib import Path

# Paths
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent

DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_DIR / "data"))
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "foods.db"))
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", PROJECT_DIR / "frontend"))

# LLM Selection: local Ollama vs Gemini API
USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "false").strip().lower() in ("true", "1", "yes")

# Ollama configuration (used when USE_LOCAL_LLM is true)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "30.0"))

# Gemini API configuration (used when USE_LOCAL_LLM is false)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "20.0"))
