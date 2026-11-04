"""Vercel entry point: the whole Lintel app as one Python function.

Accounts and projects live in Postgres (DATABASE_URL, set by the Neon integration). Without it,
the app falls back to SQLite in /tmp, which serverless functions wipe between cold starts, so
only use that for a throwaway preview.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LINTEL_DB", "/tmp/lintel.db")

from backend.app import app  # noqa: E402,F401  (Vercel serves this ASGI app)
