"""Vercel entry point: exposes the FastAPI app as a serverless function.
Background AI jobs are only *enqueued* here; a worker (worker.py) running on a
persistent host (Railway/Fly) executes them."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app  # noqa: E402,F401
