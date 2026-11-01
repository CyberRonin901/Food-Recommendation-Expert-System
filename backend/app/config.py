import os
from pathlib import Path

# Paths
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent

DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_DIR / "data"))
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "foods.db"))
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", PROJECT_DIR / "frontend"))

# Gemini API configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "20.0"))
