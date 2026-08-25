"""Vercel entry point: exposes the FastAPI app as a serverless function.

Vercel rewrites every request to this file and the ASGI app then sees the path
`/api/index.py`. vercel.json passes the original path as `__path=/…`; the
wrapper below restores `scope["path"]` (and strips the helper parameter) so
FastAPI routes work unchanged.
Background AI jobs are executed by POST /api/jobs/{id}/run (the client calls
it right after enqueue) and by the daily cron fallback."""
import os
import sys
from urllib.parse import parse_qsl, unquote, urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app as fastapi_app  # noqa: E402


async def app(scope, receive, send):
    if scope.get("type") in ("http", "websocket"):
        qs = scope.get("query_string", b"").decode("latin-1")
        pairs = parse_qsl(qs, keep_blank_values=True)
        path = next((v for k, v in pairs if k == "__path"), None)
        if path is not None:
            rest = [(k, v) for k, v in pairs if k != "__path"]
            new_path = "/" + unquote(path).lstrip("/")
            scope = dict(scope)
            scope["path"] = new_path
            scope["raw_path"] = new_path.encode()
            scope["query_string"] = urlencode(rest, doseq=True).encode()
    await fastapi_app(scope, receive, send)
