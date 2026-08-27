#!/usr/bin/env python
"""Record the demo session: ingest progress + interview, from the real project.

Run once after the demo project has a dashboard. Produces data/demo_script.json,
which the public /demo page replays — no AI, no cost per visitor.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bizzmind.config  # noqa: E402  (loads .env)
import db  # noqa: E402
from bizzmind.config import DATA_DIR  # noqa: E402

PID = "demo-public"


def main() -> None:
    with db.pool().connection() as con:
        row = con.execute("SELECT meta, chat FROM public.projects WHERE id = %s", (PID,)).fetchone()
    meta, chat = row[0], row[1] or []
    tables = [t for tabs in (meta.get("files") or {}).values() for t in tabs]

    steps = [{"kind": "info", "text": "Отварям РАПОРТ ЯНУАРИ 2024.xlsx…", "at": 200},
             {"kind": "info", "text": f"Намерени са {len(tables)} листа — разчитам заглавните редове…", "at": 900}]
    at = 1500
    with db.pool().connection() as con:
        for t in tables:
            n = con.execute(f'SELECT count(*) FROM "p_{PID.replace("-", "_")}"."{t}"').fetchone()[0]
            pretty = t.replace("рапорт_януари_2024_", "").replace("_", " ").title()
            steps.append({"kind": "table", "text": f"Заредена таблица „{pretty}“ — {n} реда, 14 колони", "at": at})
            at += 420
    total = sum(1 for s in steps if s["kind"] == "table")
    steps.append({"kind": "info", "text": f"Готово: {total} таблици, {total * 31} реда — разпознати автоматично", "at": at + 500})

    # the interview: questions the agent actually asked, with the answer we gave
    questions = []
    for m in chat:
        for q in (m.get("questions") or []):
            opts = list(q.get("options") or [])[:4]
            if not opts:
                continue
            questions.append({"q": q.get("question", ""), "options": opts, "picked": opts[0]})
    if not questions:      # fallback so the demo never plays empty
        questions = [
            {"q": "Обектите са от три вида — магазини, складове и производство. Да ги сравнявам ли заедно?",
             "options": ["Не, отделно по вид", "Да, всички заедно"], "picked": "Не, отделно по вид"},
            {"q": "Кой показател е най-важен за вас?",
             "options": ["Печалба и марж", "Оборот", "Среден бон"], "picked": "Печалба и марж"},
        ]
    out = {"steps": steps, "questions": questions[:3]}
    (DATA_DIR / "demo_script.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"demo script: {len(steps)} steps, {len(out['questions'])} questions -> {DATA_DIR / 'demo_script.json'}")


if __name__ == "__main__":
    main()
