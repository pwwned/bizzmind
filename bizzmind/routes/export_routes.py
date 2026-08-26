"""Export routes: PDF report, presentation generation, Paddle webhooks."""

from fastapi import APIRouter, Request

from bizzmind import gamma
from bizzmind.export_pdf import ExportRequest
from bizzmind import export_pdf as _pdf

router = APIRouter()


@router.post("/api/p/{pid}/export/pdf")
def export_pdf(pid: str, req: ExportRequest, request: Request):
    return _pdf.export_pdf(pid, req, request)


@router.get("/api/pres/options")
@router.get("/api/gamma/options")          # legacy path (old UI)
def gamma_options(request: Request):
    """Everything the UI needs to render the presentation controls."""
    return gamma.gamma_options(request)


@router.get("/api/p/{pid}/pres/credits")
def pres_credits(pid: str, request: Request):
    from bizzmind.project import get_project
    get_project(pid)                        # enforces org membership
    return gamma.pres_credits(pid)


@router.get("/api/pres/file/{gid}")
def pres_file(gid: str):
    return gamma.pres_file(gid)


@router.post("/api/p/{pid}/pres")
@router.post("/api/p/{pid}/gamma")          # legacy path (old UI)
def gamma_generate(pid: str, req: gamma.GammaRequest, request: Request):
    return gamma.gamma_generate(pid, req, request)


@router.get("/api/pres/status/{gid}")
@router.get("/api/gamma/status/{gid}")      # legacy path (old UI)
def gamma_status(gid: str):
    return gamma.gamma_status(gid)


@router.post("/api/webhooks/paddle")
async def paddle_webhook(request: Request):
    from bizzmind import paddle_billing
    paddle_billing.check_source_ip(request)
    raw = await request.body()
    paddle_billing.check_signature(raw, request.headers.get("paddle-signature"))
    import json as _json
    event = _json.loads(raw)
    outcome = paddle_billing.apply_event(event)
    return {"ok": True, "outcome": outcome}
