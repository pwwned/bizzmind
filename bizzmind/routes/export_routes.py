"""Export routes: PDF report and Gamma presentation generation."""

from fastapi import APIRouter, Request

from bizzmind import gamma
from bizzmind.export_pdf import ExportRequest
from bizzmind import export_pdf as _pdf

router = APIRouter()


@router.post("/api/p/{pid}/export/pdf")
def export_pdf(pid: str, req: ExportRequest, request: Request):
    return _pdf.export_pdf(pid, req, request)


@router.get("/api/gamma/options")
def gamma_options(request: Request):
    """Everything the UI needs to render Gamma's generation controls."""
    return gamma.gamma_options(request)


@router.post("/api/p/{pid}/gamma")
def gamma_generate(pid: str, req: gamma.GammaRequest, request: Request):
    return gamma.gamma_generate(pid, req, request)


@router.get("/api/gamma/status/{gid}")
def gamma_status(gid: str):
    return gamma.gamma_status(gid)
