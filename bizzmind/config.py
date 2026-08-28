"""Environment, constants and logging shared by every module."""

import logging
import os
from pathlib import Path


# "subscription": local testing via Claude Agent SDK (uses your Claude Code
# login / subscription). "api": production path via the Anthropic API.
def _load_dotenv(path: Path) -> None:
    """Tiny .env reader (KEY=VALUE, # comments) — no extra dependency."""
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


ROOT = Path(__file__).resolve().parent.parent

_load_dotenv(ROOT / ".env")

# An env var that exists but is empty (easy to do in a hosting dashboard) must
# read as "not set" — otherwise it silently selects the other backend.
AI_BACKEND = os.environ.get("AI_BACKEND", "").strip() or "subscription"
GAMMA_API_KEY = os.environ.get("GAMMA_API_KEY", "")
# Public https origin of this server — Gamma's servers fetch chart images and
# the logo from here. Without it the deck is generated text-only.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

logging.basicConfig(level=logging.INFO, format="%(asctime)s STEP | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("studio")

# On Vercel the deployment is read-only; /tmp is the only writable place. Local
# dirs are only a cache of Supabase Storage + Postgres, so losing them is fine.
DATA_DIR = Path(os.environ.get("DATA_DIR") or ("/tmp/bizzmind" if os.environ.get("VERCEL") else str(ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR = DATA_DIR / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)

MODEL = "claude-opus-5"
MAX_CHART_ROWS = 500
MAX_PREVIEW_ROWS = 50
MAX_SERIES = 8
SUB_TIMEOUT_S = 600

# INLINE_JOBS=1 runs AI tasks inside the request (tests, single-process dev).
INLINE_JOBS = os.environ.get("INLINE_JOBS", "0") == "1"

NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}


def _short(s, n=140):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + "…"
