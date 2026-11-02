"""Vercel entry point: the whole Lintel app as one Python function, in hosted demo mode.

Serverless functions only get a writable /tmp that is wiped between cold starts, so the
demo database lives there and is re-seeded with the sample clinic each time (see backend/demo.py).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LINTEL_DB", "/tmp/lintel.db")
os.environ.setdefault("LINTEL_DEMO", "1")

from backend.app import app  # noqa: E402,F401  (Vercel serves this ASGI app)
