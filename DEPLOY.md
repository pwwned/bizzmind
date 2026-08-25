# Bizzmind — деплой

## Услуги
| Компонент | Къде | Как |
|---|---|---|
| Supabase | Postgres + Auth + Storage | проект `knyznqohyvikesjtjdso` (eu-west-1); миграции в `supabase/migrations/` |
| API (FastAPI) | Railway (Docker) — или Vercel (`api/index.py`, `vercel.json`) | env от `.env.example` |
| Worker (AI задачи) | Railway — **задължително постоянен процес** | същия образ, команда `python worker.py` |
| Landing/статика | Vercel (по желание) | |

## Env променливи (API и worker)
`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_DB_URL` (pooler 6543),
`ANTHROPIC_API_KEY` + `AI_BACKEND=api` (продукция), `GAMMA_API_KEY`, `COOKIE_SECURE=1`.

## Railway
1. GitHub repo → New Project → Deploy from repo (Dockerfile се разпознава).
2. Втори service от същото repo: Settings → Start Command = `python worker.py`.
3. Variables: горните, и `PORT` се подава от Railway.

## Vercel (API само за enqueue/четене)
`vercel --prod` от корена; env променливите в Project Settings. Worker-ът остава на Railway.

## Локално
`./start.sh` — API (:8000) + worker (+ тунел). Тестове: `INLINE_JOBS=1` изпълнява AI задачите в заявката.
