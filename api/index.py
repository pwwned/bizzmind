"""Vercel entry point: exposes the FastAPI app as a serverless function.
The original request path (rewritten to this file by vercel.json) is restored
by bizzmind.path_restore.PathRestoreMiddleware inside the app."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app  # noqa: E402,F401
