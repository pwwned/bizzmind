"""Bizzmind — file storage on Supabase Storage (bucket `projects`, private).

Layout inside the bucket:
    <project id>/uploads/<file>      original spreadsheets
    <project id>/brand/<file>        brand book, logo, extracted brand.json / .txt
    <project id>/pub/<token>/<file>  assets handed to Gamma via signed URLs

The app keeps working on local directories (fast, existing code paths) and
treats them as a cache: `sync_down()` fills the cache from Storage on a cold
start (serverless instance, new machine), `sync_up()` mirrors local changes
back. Nothing important lives only on disk.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger("studio")
BUCKET = os.environ.get("SUPABASE_BUCKET", "projects")


def enabled() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"))


def _base() -> str:
    return os.environ["SUPABASE_URL"].rstrip("/") + "/storage/v1"


def _headers(extra: dict | None = None) -> dict:
    key = os.environ["SUPABASE_SERVICE_KEY"]
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    if extra:
        h.update(extra)
    return h


class StorageError(Exception):
    pass


def _req(method: str, path: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 60):
    req = urllib.request.Request(_base() + path, method=method, data=data, headers=_headers(headers))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        raise StorageError(f"{method} {path} -> {e.code}: {body}")
    except Exception as e:
        raise StorageError(f"{method} {path} -> {e}")


_CYR = {"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ж":"zh","з":"z","и":"i","й":"y",
        "к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u",
        "ф":"f","х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sht","ъ":"a","ь":"y","ю":"yu","я":"ya"}


def ascii_key(name: str) -> str:
    """Storage keys must be ASCII (Supabase rejects Cyrillic with InvalidKey).
    Transliterate, keep the extension, and stay stable for the same input."""
    import hashlib
    import re as _re
    stem, _, ext = name.rpartition(".")
    stem = stem or name
    out = []
    for ch in stem.lower():
        out.append(_CYR.get(ch, ch if (ch.isascii() and (ch.isalnum() or ch in "._- ")) else "_"))
    safe = _re.sub(r"[\s_]+", "_", "".join(out)).strip("._-")[:70] or "file"
    if safe != stem.lower():          # keep collisions apart for different originals
        safe = f"{safe}-{hashlib.sha1(name.encode()).hexdigest()[:6]}"
    ext = _re.sub(r"[^A-Za-z0-9]", "", ext)[:10]
    return f"{safe}.{ext}" if ext else safe


def _q(path: str) -> str:
    return "/".join(urllib.parse.quote(p, safe="") for p in path.split("/"))


# --------------------------------------------------------------- primitives

def put(path: str, data: bytes, content_type: str | None = None) -> None:
    ct = content_type or mimetypes.guess_type(path)[0] or "application/octet-stream"
    _req("POST", f"/object/{BUCKET}/{_q(path)}", data,
         {"Content-Type": ct, "x-upsert": "true", "Cache-Control": "3600"})


def get(path: str) -> bytes:
    return _req("GET", f"/object/{BUCKET}/{_q(path)}")[1]


def list_dir(prefix: str) -> list[dict]:
    """Objects directly under prefix: [{name, size}] (folders are skipped)."""
    out, offset = [], 0
    while True:
        body = json.dumps({"prefix": prefix.rstrip("/"), "limit": 200, "offset": offset,
                           "sortBy": {"column": "name", "order": "asc"}}).encode()
        _, raw = _req("POST", f"/object/list/{BUCKET}", body, {"Content-Type": "application/json"})
        items = json.loads(raw or b"[]")
        for it in items:
            if it.get("id") is None:      # folder placeholder
                continue
            out.append({"name": it["name"], "size": (it.get("metadata") or {}).get("size", -1)})
        if len(items) < 200:
            return out
        offset += 200


def delete(paths: list[str]) -> None:
    if not paths:
        return
    _req("DELETE", f"/object/{BUCKET}", json.dumps({"prefixes": paths}).encode(),
         {"Content-Type": "application/json"})


def delete_prefix(prefix: str) -> int:
    """Remove everything under prefix (walks one level of sub-folders we use)."""
    n = 0
    for sub in ("uploads", "brand", "pub"):
        items = list_dir(f"{prefix}/{sub}")
        paths = [f"{prefix}/{sub}/{it['name']}" for it in items]
        if sub == "pub":   # pub has token folders
            _, raw = _req("POST", f"/object/list/{BUCKET}",
                          json.dumps({"prefix": f"{prefix}/pub", "limit": 500}).encode(),
                          {"Content-Type": "application/json"})
            for folder in json.loads(raw or b"[]"):
                if folder.get("id") is None:
                    paths += [f"{prefix}/pub/{folder['name']}/{it['name']}"
                              for it in list_dir(f"{prefix}/pub/{folder['name']}")]
        delete(paths)
        n += len(paths)
    return n


def signed_url(path: str, expires_s: int = 7 * 24 * 3600) -> str:
    _, raw = _req("POST", f"/object/sign/{BUCKET}/{_q(path)}",
                  json.dumps({"expiresIn": expires_s}).encode(), {"Content-Type": "application/json"})
    rel = json.loads(raw)["signedURL"]
    return _base() + (rel if rel.startswith("/") else "/" + rel)


def signed_upload_url(path: str, upsert: bool = True) -> str:
    """URL the browser can PUT a file to (bypasses API body-size limits)."""
    _, raw = _req("POST", f"/object/upload/sign/{BUCKET}/{_q(path)}", b"{}",
                  {"Content-Type": "application/json", **({"x-upsert": "true"} if upsert else {})})
    d = json.loads(raw)
    tok = d.get("token")
    return f"{_base()}/object/upload/sign/{BUCKET}/{_q(path)}?token={urllib.parse.quote(tok, safe='')}"


# --------------------------------------------------------------- cache sync

def sync_down(pid: str, sub: str, local: Path) -> int:
    """Pull files missing locally (or with a different size). Returns count."""
    if not enabled():
        return 0
    local.mkdir(parents=True, exist_ok=True)
    try:
        remote = list_dir(f"{pid}/{sub}")
    except StorageError as e:
        log.info(f"[{pid}] storage: list {sub} failed — {e}")
        return 0
    n = 0
    for it in remote:
        f = local / it["name"]
        if f.exists() and (it["size"] < 0 or f.stat().st_size == it["size"]):
            continue
        try:
            f.write_bytes(get(f"{pid}/{sub}/{it['name']}"))
            n += 1
        except StorageError as e:
            log.info(f"[{pid}] storage: get {it['name']} failed — {e}")
    if n:
        log.info(f"[{pid}] storage: pulled {n} file(s) into {sub}/")
    return n


def sync_up(pid: str, sub: str, local: Path) -> int:
    """Mirror the local directory to Storage: upload changed files, delete
    remote files that no longer exist locally. Returns files touched."""
    if not enabled():
        return 0
    local.mkdir(parents=True, exist_ok=True)
    try:
        remote = {it["name"]: it["size"] for it in list_dir(f"{pid}/{sub}")}
    except StorageError as e:
        log.info(f"[{pid}] storage: list {sub} failed — {e}")
        return 0
    n = 0
    local_names = set()
    for f in sorted(local.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        local_names.add(ascii_key(f.name))
        key = ascii_key(f.name)
        if remote.get(key) == f.stat().st_size:
            continue
        try:
            put(f"{pid}/{sub}/{key}", f.read_bytes())
            n += 1
        except StorageError as e:
            log.info(f"[{pid}] storage: put {f.name} failed — {e}")
    stale = [f"{pid}/{sub}/{name}" for name in remote if name not in local_names]
    if stale and not local_names:
        # an empty local cache (fresh process) must NEVER wipe the remote copy —
        # deletions are only mirrored when the local dir has real content
        log.info(f"[{pid}] storage: local {sub}/ empty, keeping {len(stale)} remote file(s)")
        stale = []
    if stale:
        try:
            delete(stale)
            n += len(stale)
        except StorageError as e:
            log.info(f"[{pid}] storage: delete failed — {e}")
    if n:
        log.info(f"[{pid}] storage: synced {n} change(s) in {sub}/")
    return n
