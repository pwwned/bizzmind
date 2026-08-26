"""Paddle Billing webhooks: verified deliveries update the org's plan and
credits. Security: IP allowlist fetched live from Paddle's /ips endpoint
(never hard-coded) + HMAC signature check with the endpoint's secret key.
Idempotency via public.webhook_events (one row per Paddle event id)."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import time
import urllib.request

from fastapi import HTTPException, Request

from bizzmind.config import log
from bizzmind.plans import PLANS, TRIAL_CREDITS
from db import pool


def _sandbox() -> bool:
    return os.environ.get("PADDLE_API_KEY", "").startswith("pdl_sdbx_")


def _api_base() -> str:
    return "https://sandbox-api.paddle.com" if _sandbox() else "https://api.paddle.com"


def api(method: str, path: str, body: dict | None = None) -> dict:
    """Server-side Paddle API call (management operations)."""
    key = os.environ["PADDLE_API_KEY"]
    req = urllib.request.Request(_api_base() + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["data"]
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        log.info(f"paddle api {method} {path} -> {e.code}: {detail}")
        raise HTTPException(502, "billing operation failed")


# ------------------------------------------------------------- IP allowlist

_ips_cache: dict = {"at": 0.0, "nets": []}


def _allowed_networks() -> list:
    if time.time() - _ips_cache["at"] > 3600 or not _ips_cache["nets"]:
        req = urllib.request.Request(_api_base() + "/ips",
                                     headers={"User-Agent": "Bizzmind/1.0 (+https://bizzmind.ai)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            cidrs = json.loads(r.read())["data"]["ipv4_cidrs"]
        _ips_cache.update(at=time.time(), nets=[ipaddress.ip_network(c) for c in cidrs])
        log.info(f"paddle: IP allowlist refreshed — {len(cidrs)} networks")
    return _ips_cache["nets"]


def check_source_ip(request: Request) -> None:
    ip = (request.headers.get("x-real-ip")
          or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
          or (request.client.host if request.client else ""))
    if ip in ("127.0.0.1", "::1"):          # local integration tests
        return
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        raise HTTPException(403, "bad source address")
    if not any(addr in net for net in _allowed_networks()):
        log.info(f"paddle: webhook from unlisted IP {ip} rejected")
        raise HTTPException(403, "source not allowed")


# ------------------------------------------------------------- signature

def check_signature(raw: bytes, header: str | None) -> None:
    secret = os.environ.get("PADDLE_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(503, "webhook secret not configured")
    if not header:
        raise HTTPException(403, "missing signature")
    parts = dict(p.split("=", 1) for p in header.split(";") if "=" in p)
    ts, h1 = parts.get("ts", ""), parts.get("h1", "")
    if not ts or not h1 or abs(time.time() - int(ts)) > 300:
        raise HTTPException(403, "stale or malformed signature")
    digest = hmac.new(secret.encode(), f"{ts}:".encode() + raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, h1):
        raise HTTPException(403, "signature mismatch")


# ------------------------------------------------------------- apply events

def _org_by_email(con, email: str):
    row = con.execute(
        "SELECT m.org_id FROM public.memberships m JOIN auth.users u ON u.id = m.user_id "
        "WHERE lower(u.email) = lower(%s) ORDER BY m.created_at LIMIT 1", (email,)).fetchone()
    return row[0] if row else None


def _customer_email(customer_id: str) -> str:
    key = os.environ["PADDLE_API_KEY"]
    req = urllib.request.Request(f"{_api_base()}/customers/{customer_id}",
                                 headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["data"].get("email", "")


def _resolve_org(con, data: dict):
    org = (data.get("custom_data") or {}).get("org_id")
    if org:
        return org
    cust = data.get("customer_id")
    if cust:
        row = con.execute("SELECT id FROM public.organizations WHERE paddle_customer_id = %s",
                          (cust,)).fetchone()
        if row:
            return row[0]
        try:
            email = _customer_email(cust)
            if email:
                return _org_by_email(con, email)
        except Exception as e:
            log.info(f"paddle: customer lookup failed — {e}")
    return None


def apply_event(event: dict) -> str:
    etype = event.get("event_type", "")
    data = event.get("data") or {}
    eid = event.get("event_id", "")
    with pool().connection() as con:
        if eid:
            fresh = con.execute(
                "INSERT INTO public.webhook_events (id, type) VALUES (%s, %s) "
                "ON CONFLICT (id) DO NOTHING RETURNING 1", (eid, etype)).fetchone()
            if not fresh:
                return "duplicate"

        if etype.startswith("subscription."):
            org = _resolve_org(con, data)
            if org is None:
                log.info(f"paddle: {etype} — no org match (sub {data.get('id')})")
                return "no-org"
            status = data.get("status", "")
            items = data.get("items") or []
            plan_key = next((((i.get("price") or {}).get("custom_data") or {}).get("plan")
                             for i in items
                             if ((i.get("price") or {}).get("custom_data") or {}).get("plan")), None)
            if status in ("active", "trialing") and plan_key in PLANS:
                p = PLANS[plan_key]
                quota = min(p["credits"], TRIAL_CREDITS) if status == "trialing" else p["credits"]
                con.execute(
                    "UPDATE public.organizations SET plan = %s, credits_quota = %s, credits_used = 0, "
                    "credits_renewed_at = now(), paddle_customer_id = %s, paddle_subscription_id = %s "
                    "WHERE id = %s",
                    (plan_key, quota, data.get("customer_id"), data.get("id"), org))
                log.info(f"paddle: org {org} -> {plan_key} ({status})")
                return f"plan:{plan_key}"
            if status in ("canceled", "paused", "past_due"):
                free = PLANS["free"]["credits"]
                con.execute(
                    "UPDATE public.organizations SET plan = 'free', "
                    "credits_quota = LEAST(credits_quota, %s), paddle_subscription_id = NULL "
                    "WHERE id = %s", (free, org))
                log.info(f"paddle: org {org} downgraded to free ({status})")
                return "plan:free"
            return "ignored-status"

        if etype == "transaction.completed":
            org = _resolve_org(con, data)
            credits = 0
            for item in data.get("items") or []:
                cd = ((item.get("price") or {}).get("custom_data") or {})
                if cd.get("credits"):
                    credits += int(cd["credits"]) * int(item.get("quantity") or 1)
            if credits and org is not None:
                con.execute(
                    "UPDATE public.organizations SET credits_extra = credits_extra + %s, "
                    "paddle_customer_id = COALESCE(paddle_customer_id, %s) WHERE id = %s",
                    (credits, data.get("customer_id"), org))
                log.info(f"paddle: org {org} +{credits} credits (packs)")
                return f"credits:{credits}"
            return "no-credits" if org is not None else "no-org"

    return "ignored"
