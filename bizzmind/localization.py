"""Content localization: the AI writes dashboards in the UI language of the
moment; switching language translates the texts once and caches them."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from bizzmind.data import filters_with_options

if TYPE_CHECKING:
    from bizzmind.project import Project


# ------------------------------------------------- content localization
# Dashboards are written by the AI in the UI language of the moment. When the
# user switches language, every text the dashboard carries (chart titles,
# insights, filter labels, notes, field names, textual values) is translated
# ONCE by the AI and cached in the project (i18n_<lang>.json, keyed by a hash
# of the source text so edits invalidate only what changed). /state serves
# the translated view; the frontend maps field/value labels at render time.

def _cyr_ratio(texts) -> float:
    s = " ".join(t for t in texts if isinstance(t, str))
    letters = [ch for ch in s if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if "Ѐ" <= ch <= "ӿ") / len(letters)


def content_lang(proj: Project) -> str:
    texts = [c.get("title", "") for c in proj.dashboard] + [f.get("label", "") for f in proj.filters]
    if not texts:
        return "bg"
    return "bg" if _cyr_ratio(texts) > 0.5 else "en"


def _h(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def _load_i18n(proj: Project, lang: str) -> dict:
    return dict(proj.i18n.get(lang) or {})


def _save_i18n(proj: Project, lang: str, tr: dict) -> None:
    proj.i18n[lang] = tr
    proj.save_i18n()


def _has_letters(v) -> bool:
    return isinstance(v, str) and any(ch.isalpha() for ch in v) and not v.strip().isdigit()


def translatable_items(proj: Project, lang: str | None = None) -> dict:
    """Every source text of the project that the UI shows, keyed by hash."""
    items: dict = {}

    def add(text):
        if _has_letters(text) and len(text) <= 1200:
            items[_h(text)] = text
    for c in proj.dashboard:
        add(c.get("title", ""))
        add(c.get("insight", ""))
        add(c.get("x_field", ""))
        for y in c.get("y_fields", []) or []:
            add(y)
        n = 0
        for r in c.get("rows") or []:
            for v in r.values():
                if _has_letters(v) and n < 400:
                    add(v)
                    n += 1
    for f in proj.filters:
        add(f.get("label", ""))
        for o in (f.get("options") or [])[:60]:
            if isinstance(o, dict):
                add(o.get("label", ""))
            else:
                add(o)
    for n in proj.notes:
        add(n)
    for v in (proj.meta.get("views") or {}).values():
        if isinstance(v, dict):
            add(v.get("description", ""))
    # textual values first seen in filtered re-runs (see localize_charts)
    for v in list(getattr(proj, "i18n_pending", {}).get(lang, set()) if lang else []):
        add(v)
    return items


def localize_charts(proj: Project, lang: str, tr: dict, charts: list):
    """Translate title/insight and every textual cell of the given charts with
    the cached map. Values without a translation are queued so the next
    /translate run picks them up (filters reveal values the stored sample
    did not contain). Returns (charts, field_labels, value_labels, pending)."""
    if not hasattr(proj, "i18n_pending"):
        proj.i18n_pending = {}
    pending = proj.i18n_pending.setdefault(lang, set())
    fields, values = {}, {}
    out = []
    for c in charts:
        cc = dict(c)
        for k in ("title", "insight"):
            if _has_letters(c.get(k)):
                cc[k] = tr.get(_h(c[k]), c[k])
        for name in [c.get("x_field", "")] + list(c.get("y_fields") or []):
            if _has_letters(name) and _h(name) in tr:
                fields[name] = tr[_h(name)]
        for r in c.get("rows") or []:
            for v in r.values():
                if _has_letters(v):
                    t = tr.get(_h(v))
                    if t is not None:
                        values[v] = t
                    elif len(pending) < 600 and v not in pending and len(v) <= 1200:
                        pending.add(v)
        out.append(cc)
    return out, fields, values, pending


def localized_content(proj: Project, lang: str):
    """(charts, notes, filters, i18n_info) for the UI language."""
    src = content_lang(proj)
    filters = filters_with_options(proj)
    info = {"content_lang": src, "ui_lang": lang, "needs_translation": False,
            "field_labels": {}, "value_labels": {}}
    if lang == src or (not proj.dashboard and not proj.notes):
        return proj.dashboard, proj.notes, filters, info
    tr = _load_i18n(proj, lang)
    charts, info["field_labels"], info["value_labels"], _ = localize_charts(proj, lang, tr, proj.dashboard)
    items = translatable_items(proj, lang)
    missing = [k for k in items if k not in tr]
    info["needs_translation"] = bool(missing)
    info["missing"] = len(missing)

    def tx(text):
        return tr.get(_h(text), text) if isinstance(text, str) else text
    fl = []
    for f in filters:
        ff = dict(f)
        ff["label"] = tx(f.get("label", ""))
        fl.append(ff)
        for o in (f.get("options") or []):
            lab = o.get("label") if isinstance(o, dict) else o
            if _has_letters(lab) and _h(lab) in tr:
                info["value_labels"][lab] = tr[_h(lab)]
    notes = [tx(n) for n in proj.notes]
    return charts, notes, fl, info
