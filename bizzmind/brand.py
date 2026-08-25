"""Brand assets: files, colours, fonts and logo derived from the uploaded brand book."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from bizzmind.config import _short, log
from bizzmind.i18n import T

if TYPE_CHECKING:
    from bizzmind.project import Project

NAVY = (8 / 255, 32 / 255, 66 / 255)
NAVY_DEEP = (4 / 255, 20 / 255, 44 / 255)
CYAN = (10 / 255, 221 / 255, 245 / 255)


# ------------------------------------------------------------ brand assets

BRAND_EXTS = (".pdf", ".png", ".jpg", ".jpeg", ".svg")


def brand_dir(proj: Project) -> Path:
    d = proj.dir / "brand"
    d.mkdir(exist_ok=True)
    return d


def brand_files(proj: Project) -> list:
    d = brand_dir(proj)
    return sorted(f.name for f in d.iterdir()
                  if f.suffix.lower() in BRAND_EXTS)


def brand_logo_path(proj: Project) -> Path | None:
    d = brand_dir(proj)
    imgs = [f for f in sorted(d.iterdir())
            if f.suffix.lower() in (".png", ".jpg", ".jpeg") and not f.name.startswith("_")]
    return imgs[0] if imgs else None


def brand_colors(proj: Project) -> list:
    p = brand_dir(proj) / "brand.json"
    try:
        return json.loads(p.read_text()).get("colors", []) if p.exists() else []
    except Exception:
        return []


def brand_theme(proj: Project) -> tuple:
    """(primary, accent) RGB from the brand book's hex codes; falls back to
    Inceptiq navy/cyan. Primary = darkest colour, accent = most vivid."""
    import colorsys
    p = brand_dir(proj) / "brand.json"
    primary, accent = NAVY_DEEP, CYAN
    try:
        if p.exists():
            hexes = json.loads(p.read_text()).get("colors", [])
            rgbs = [tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)) for h in hexes]
            rgbs = [r for r in rgbs if r != (1, 1, 1) and r != (0, 0, 0)]
            if rgbs:
                primary = min(rgbs, key=sum)

                def vivid(r):
                    h, l, s = colorsys.rgb_to_hls(*r)
                    return s * (1 - abs(l - 0.55))
                pool = [r for r in rgbs if r != primary] or rgbs
                accent = max(pool, key=vivid)
    except Exception:
        pass
    return primary, accent


def brand_excerpt(proj: Project, limit: int = 2500) -> str:
    """Concatenated text extracted from uploaded brand PDFs (for AI context)."""
    parts = []
    for f in sorted(brand_dir(proj).glob("*.txt")):
        try:
            parts.append(f"[{f.stem}]\n{f.read_text()[:limit]}")
        except Exception:
            continue
    return "\n\n".join(parts)[:limit]


def _prepare_logo(path: Path) -> Path:
    """Make an extracted logo usable: if it is a whole logo sheet, crop to the
    first (primary) logo on it; turn the white background transparent so the
    logo sits cleanly on dark covers. Saves as PNG."""
    try:
        import numpy as np
        from PIL import Image
        im = Image.open(path).convert("RGBA")
        a = np.array(im)
        nonwhite = (a[..., :3] < 235).any(axis=2) & (a[..., 3] > 40)
        # density thresholds: thin caption lines between logos count as gaps
        rows = nonwhite.mean(axis=1) > 0.004
        if not rows.any():
            rows = nonwhite.any(axis=1)
        if not rows.any():
            return path
        ys = np.where(rows)[0]
        # first contiguous horizontal band of content (gap tolerance ~1.5% height)
        gap_y = max(10, im.height // 60)
        y0, y1 = int(ys[0]), int(ys[0])
        for y in ys:
            if y - y1 <= gap_y:
                y1 = int(y)
            else:
                break
        band = nonwhite[y0:y1 + 1]
        cols_d = band.mean(axis=0) > 0.004
        xs = np.where(cols_d)[0] if cols_d.any() else np.where(band.any(axis=0))[0]
        gap_x = max(14, im.width // 40)
        x0, x1 = int(xs[0]), int(xs[0])
        for x in xs:
            if x - x1 <= gap_x:
                x1 = int(x)
            else:
                break
        # degenerate crop -> fall back to the bbox of everything
        if (x1 - x0) < im.width * 0.1 or (y1 - y0) < 16:
            xs_all = np.where(nonwhite.any(axis=0))[0]
            x0, x1, y0, y1 = int(xs_all[0]), int(xs_all[-1]), int(ys[0]), int(ys[-1])
        pad = 16
        crop = im.crop((max(0, x0 - pad), max(0, y0 - pad),
                        min(im.width, x1 + pad), min(im.height, y1 + pad)))
        arr = np.array(crop)
        arr[(arr[..., :3] > 242).all(axis=2), 3] = 0   # white -> transparent
        out = path.parent / (path.stem + ".png")
        Image.fromarray(arr).save(out)
        if out != path and path.exists():
            path.unlink()
        return out
    except Exception as e:
        log.info(f"logo prepare failed — {_short(e)}")
        return path


def extract_brand_assets(proj: Project):
    """Text, colours and a usable logo out of the uploaded brand files.
    Idempotent — runs on upload and as a backfill for older uploads."""
    import re as _re
    import subprocess
    d = brand_dir(proj)
    pdfs = sorted(d.glob("*.pdf"))

    # 1) text from every brand PDF
    for f in pdfs:
        txt = d / (f.stem + ".txt")
        if txt.exists():
            continue
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(f))
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:8])
            txt.write_text(text.strip()[:20000])
        except Exception as e:
            log.info(f"[{proj.id}] brand: text extract failed for '{f.name}' — {_short(e)}")

    # 2) colours: hex codes and "R: 2 G: 59 B: 89" style breakdowns
    hexes: list = []
    for txt in sorted(d.glob("*.txt")):
        try:
            t = txt.read_text()
        except Exception:
            continue
        hexes += [h.upper() for h in _re.findall(r"#[0-9a-fA-F]{6}", t)]
        for r, g, b in _re.findall(
                r"R:?\s*(\d{1,3})[,;\s]+G:?\s*(\d{1,3})[,;\s]+B:?\s*(\d{1,3})", t):
            if all(int(v) <= 255 for v in (r, g, b)):
                hexes.append("#%02X%02X%02X" % (int(r), int(g), int(b)))
    hexes = list(dict.fromkeys(hexes))[:12]

    # fonts: scan the book text against known typeface names, in order of
    # first appearance (first mention is usually the primary typeface)
    KNOWN_FONTS = [
        "IBM Plex Sans", "IBM Plex Serif", "Helvetica Neue", "Helvetica",
        "Roboto Condensed", "Roboto Slab", "Roboto", "Inter", "Montserrat",
        "Open Sans", "Source Sans", "Noto Sans", "Lato", "Poppins", "Raleway",
        "Work Sans", "DM Sans", "PT Sans", "Nunito Sans", "Nunito", "Manrope",
        "Rubik", "Ubuntu", "Mulish", "Barlow", "Karla", "Georgia", "Garamond",
        "Playfair Display", "Merriweather", "Arial", "Verdana", "Futura",
        "Gotham", "Proxima Nova", "Avenir",
    ]
    all_text = "\n".join(t.read_text() for t in sorted(d.glob("*.txt")) if t.exists())
    found, names = [], []
    low = all_text.lower()
    for fam in KNOWN_FONTS:
        m = _re.search(r"\b" + _re.escape(fam.lower()) + r"\b", low)
        if m and not any(fam in n for n in names):
            found.append((m.start(), fam))
            names.append(fam)
    fonts = [fam for _, fam in sorted(found)][:3]

    if hexes or fonts:
        had = (d / "brand.json").exists()
        (d / "brand.json").write_text(json.dumps({"colors": hexes, "fonts": fonts}))
        log.info(f"[{proj.id}] brand: colours: {hexes} | fonts: {fonts}")
        if not had:
            proj.log_activity("info", T(proj.lang, "act_brand_extracted",
                                        colors=len(hexes), fonts=len(fonts)))
