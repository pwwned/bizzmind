"""Brand file upload / download / delete."""

from pathlib import Path

import storage
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from bizzmind.config import _short, log
from bizzmind.i18n import T, req_lang
from bizzmind.project import get_project
from bizzmind.brand import BRAND_EXTS, brand_dir, brand_files, extract_brand_assets

router = APIRouter()


    # Logos are NEVER auto-extracted from the book — the logo is whatever
    # image the user uploads explicitly. The book contributes colours only.


@router.post("/api/p/{pid}/brand")
async def brand_upload(pid: str, request: Request, files: list[UploadFile] = File(...)):
    proj = get_project(pid)
    lang = req_lang(request)
    proj.lang = lang
    d = brand_dir(proj)
    saved = []
    for f in files:
        fname = Path(f.filename).name
        if Path(fname).suffix.lower() not in BRAND_EXTS:
            raise HTTPException(400, T(lang, "err_brand_ext", name=fname))
        payload = await f.read()
        (d / fname).write_bytes(payload)
        saved.append(fname)
        log.info(f"[{pid}] brand: uploaded '{fname}' ({len(payload) // 1024} KB)")
        proj.log_activity("info", T(lang, "act_brand_file", name=fname))
    # a new PDF replaces previously auto-extracted assets (explicit images stay)
    if any(s.lower().endswith(".pdf") for s in saved):
        for stale in brand_dir(proj).glob("_logo_from_book.*"):
            stale.unlink()
        for s in saved:   # re-extract text of re-uploaded books
            if s.lower().endswith(".pdf"):
                stale_txt = brand_dir(proj) / (Path(s).stem + ".txt")
                if stale_txt.exists():
                    stale_txt.unlink()
    extract_brand_assets(proj)
    await run_in_threadpool(storage.sync_up, pid, "brand", brand_dir(proj))
    return {"brand": brand_files(proj), "saved": saved}


@router.get("/api/p/{pid}/brand/file/{filename}")
def brand_file(pid: str, filename: str, request: Request):
    proj = get_project(pid)
    f = brand_dir(proj) / Path(filename).name
    if not f.exists():
        raise HTTPException(404, T(req_lang(request), "err_brand_missing"))
    return FileResponse(f)


@router.delete("/api/p/{pid}/brand/{filename}")
def brand_delete(pid: str, filename: str):
    proj = get_project(pid)
    fname = Path(filename).name
    d = brand_dir(proj)
    for p in [d / fname, d / (Path(fname).stem + ".txt")]:
        if p.exists():
            p.unlink()
    storage.sync_up(pid, "brand", d)
    log.info(f"[{pid}] brand: deleted '{fname}'")
    return {"brand": brand_files(proj)}
