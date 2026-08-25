"""ASGI middleware: restore the original request path behind a hosting rewrite.

Vercel rewrites every request to api/index.py and the app sees the path
`/api/index.py`; vercel.json forwards the real path as `?__path=…`. This
middleware puts it back into scope["path"] and strips the helper parameter, so
routing works exactly as on uvicorn. No-op when the parameter is absent."""
from urllib.parse import parse_qsl, unquote, urlencode


class PathRestoreMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            qs = scope.get("query_string", b"").decode("latin-1")
            if "__path=" in qs:
                pairs = parse_qsl(qs, keep_blank_values=True)
                path = next((v for k, v in pairs if k == "__path"), None)
                if path is not None:
                    rest = [(k, v) for k, v in pairs if k != "__path"]
                    new_path = "/" + unquote(path).lstrip("/")
                    scope = dict(scope)
                    scope["path"] = new_path
                    scope["raw_path"] = new_path.encode()
                    scope["query_string"] = urlencode(rest, doseq=True).encode()
        await self.app(scope, receive, send)
