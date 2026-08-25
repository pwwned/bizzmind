"""PDF export of the dashboard (reportlab)."""

import time
from pathlib import Path

from fastapi import Request
from pydantic import BaseModel

from bizzmind.config import _short, log
from bizzmind.i18n import T, req_lang
from bizzmind.project import get_project
from bizzmind.brand import brand_logo_path, brand_theme


def _register_pdf_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if "Brand" in pdfmetrics.getRegisteredFontNames():
        return
    reg = "/System/Library/Fonts/Supplemental/Arial.ttf"
    bold = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    pdfmetrics.registerFont(TTFont("Brand", reg))
    pdfmetrics.registerFont(TTFont("Brand-Bold", bold if Path(bold).exists() else reg))


class ExportChart(BaseModel):
    title: str
    insight: str = ""
    chart_type: str
    image: str | None = None          # dataURL PNG for chart types
    columns: list[str] | None = None  # for table charts
    rows: list[list] | None = None


class ExportRequest(BaseModel):
    charts: list[ExportChart]
    filters_line: str = ""


def export_pdf(pid: str, req: ExportRequest, request: Request):
    import base64
    import io as _io

    from fastapi.responses import Response
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors as rl

    proj = get_project(pid)
    lang = req_lang(request)
    proj.lang = lang
    _register_pdf_fonts()
    PRIMARY, ACCENT = brand_theme(proj)
    W, H = landscape(A4)
    M = 40                               # page margin
    buf = _io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=(W, H))
    today = time.strftime(T(lang, "date_fmt"))

    def wrap(text, font, size, maxw, max_lines):
        words, line, lines = text.split(), "", []
        for w_ in words:
            t = (line + " " + w_).strip()
            if c.stringWidth(t, font, size) <= maxw:
                line = t
            else:
                lines.append(line)
                line = w_
                if len(lines) == max_lines:
                    return lines
        if line:
            lines.append(line)
        return lines[:max_lines]

    def page_chrome(page_no):
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, W, H, stroke=0, fill=1)
        c.setFillColorRGB(*ACCENT)
        c.rect(0, H - 5, W, 5, stroke=0, fill=1)
        c.setFillColorRGB(*PRIMARY)
        c.setFont("Brand-Bold", 10)
        c.drawString(M, H - 26, proj.meta["name"])
        c.setFont("Brand", 8)
        c.setFillColorRGB(0.55, 0.58, 0.62)
        c.drawRightString(W - M, H - 26, f"{T(lang, 'pdf_report')} · {today}")
        c.drawRightString(W - M, 18, T(lang, "pdf_page", n=page_no))

    def draw_chart_cell(ch, x0, y0, cw, chh):
        c.setFillColorRGB(*PRIMARY)
        c.setFont("Brand-Bold", 12)
        c.drawString(x0, y0 + chh - 14, _short(ch.title, int(cw / 6)))
        ty = y0 + chh - 30
        if ch.insight:
            c.setFillColorRGB(0.35, 0.39, 0.45)
            c.setFont("Brand", 8.5)
            for ln in wrap(ch.insight, "Brand", 8.5, cw, 2):
                c.drawString(x0, ty, ln)
                ty -= 11
        img_top = ty - 4
        img_h = img_top - y0
        if ch.image:
            try:
                raw = base64.b64decode(ch.image.split(",", 1)[1])
                img = ImageReader(_io.BytesIO(raw))
                iw, ih = img.getSize()
                scale = min(cw / iw, img_h / ih)
                dw, dh = iw * scale, ih * scale
                c.drawImage(img, x0 + (cw - dw) / 2, img_top - dh, dw, dh, mask="auto")
            except Exception as e:
                log.info(f"[{pid}] export: image failed — {_short(e)}")

    # ---- title page (white, so the brand logo shows in its own colours)
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColorRGB(*ACCENT)
    c.rect(0, H - 8, W, 8, stroke=0, fill=1)
    c.setFillColorRGB(*PRIMARY)
    c.rect(0, 0, W, 3, stroke=0, fill=1)
    logo = brand_logo_path(proj)
    y_center = H / 2 + 30
    if logo:
        try:
            img = ImageReader(str(logo))
            iw, ih = img.getSize()
            lw = min(230, W * 0.28)
            lh = lw * ih / iw
            if lh > 130:
                lh, lw = 130, 130 * iw / ih
            c.drawImage(img, (W - lw) / 2, y_center + 36, lw, lh,
                        preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    c.setFillColorRGB(*PRIMARY)
    c.setFont("Brand-Bold", 32)
    c.drawCentredString(W / 2, y_center - 16, proj.meta["name"])
    c.setFont("Brand", 15)
    c.setFillColorRGB(*ACCENT)
    c.drawCentredString(W / 2, y_center - 50, T(lang, "pdf_report"))
    c.setFillColorRGB(0.45, 0.49, 0.54)
    c.setFont("Brand", 11)
    c.drawCentredString(W / 2, y_center - 78, today)
    if req.filters_line:
        c.drawCentredString(W / 2, y_center - 98, T(lang, "pdf_filters", text=_short(req.filters_line, 110)))
    c.showPage()

    # ---- content: tables get a full page; charts go two per page
    page = 2
    tables = [ch for ch in req.charts if ch.columns is not None]
    charts = [ch for ch in req.charts if ch.image]

    for ch in tables:
        page_chrome(page)
        c.setFillColorRGB(*PRIMARY)
        c.setFont("Brand-Bold", 15)
        c.drawString(M, H - 58, _short(ch.title, 90))
        top = H - 74
        if ch.insight:
            c.setFillColorRGB(0.35, 0.39, 0.45)
            c.setFont("Brand", 9.5)
            for ln in wrap(ch.insight, "Brand", 9.5, W - 2 * M, 2):
                c.drawString(M, top, ln)
                top -= 13
            top -= 4
        data = [ch.columns] + [[("" if v is None else str(v)) for v in r]
                               for r in (ch.rows or [])[:15]]
        col_w = (W - 2 * M) / max(1, len(ch.columns))
        tbl = Table(data, colWidths=[col_w] * len(ch.columns))
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Brand"),
            ("FONTNAME", (0, 0), (-1, 0), "Brand-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), rl.white),
            ("BACKGROUND", (0, 0), (-1, 0), rl.Color(*PRIMARY)),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl.white, rl.Color(0.958, 0.966, 0.974)]),
            ("TEXTCOLOR", (0, 1), (-1, -1), rl.Color(0.2, 0.24, 0.3)),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, rl.Color(*ACCENT)),
            ("GRID", (0, 0), (-1, -1), 0.3, rl.Color(0.87, 0.89, 0.92)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        tw, th = tbl.wrapOn(c, W - 2 * M, top - 40)
        tbl.drawOn(c, M, max(34, top - th))
        c.showPage()
        page += 1

    cw = (W - 2 * M - 28) / 2
    chh = H - 110
    for i in range(0, len(charts), 2):
        page_chrome(page)
        draw_chart_cell(charts[i], M, 40, cw, chh)
        if i + 1 < len(charts):
            c.setStrokeColorRGB(0.9, 0.91, 0.93)
            c.setLineWidth(0.6)
            c.line(W / 2, 46, W / 2, H - 52)
            draw_chart_cell(charts[i + 1], M + cw + 28, 40, cw, chh)
        c.showPage()
        page += 1

    c.save()
    pdf = buf.getvalue()
    log.info(f"[{pid}] export: PDF generated — {len(req.charts)} страници графики, {len(pdf) // 1024} KB")
    proj.log_activity("info", T(lang, "act_pdf", n=len(req.charts)))
    fname = f"{proj.id}-report.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
