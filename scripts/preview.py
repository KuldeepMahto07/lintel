"""Run Lintel on port 8022 against a throwaway preview database (data/preview.db), for UI checks.

    .venv\\Scripts\\python scripts\\preview.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LINTEL_DB", str(ROOT / "data" / "preview.db"))
os.environ.setdefault("APP_URL", "http://127.0.0.1:8022")

import uvicorn  # noqa: E402

uvicorn.run("backend.app:app", host="127.0.0.1", port=8022)
