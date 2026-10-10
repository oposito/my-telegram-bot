"""Клиент xRocket Pay API (https://pay.xrocket.tg/api)."""
import logging
import time

from app import config, settings
from app.services.http import session

log = logging.getLogger(__name__)
_coins: tuple[list[dict], float] = ([], 0.0)


def token() -> str:
    return settings.get("xrocket_token").strip() or config.XROCKET_API_KEY


def enabled() -> bool:
    return bool(token()) and settings.get_bool("pay_crypto")


async def _req(method: str, path: str, **kw) -> dict:
    headers = {"Rocket-Pay-Key": token(), "Content-Type": "application/json"}
    async with session().request(method, config.XROCKET_API_URL + path, headers=headers, **kw) as r:
        data = await r.json(content_type=None)
        if not data.get("success"):
            raise RuntimeError(f"xRocket {path}: {data}")
        return data["data"]


async def coins() -> list[dict]:
    global _coins
    if _coins[0] and time.time() - _coins[1] < 3600:
        return _coins[0]
    async with session().get(config.XROCKET_API_URL + "/currencies/available") as r:
        data = await r.json(content_type=None)
    res = data.get("data", {}).get("results", [])
    _coins = (res, time.time())
    return res


async def allowed_coins() -> list[dict]:
    allc = await coins()
    raw = settings.get("crypto_currencies").strip()
    if not raw or raw.upper() == "ALL":
        return allc
    wanted = [c.strip().upper() for c in raw.split(",") if c.strip()]
    by = {c["currency"].upper(): c for c in allc}
    return [by[w] for w in wanted if w in by]


async def create_invoice(amount: float, currency: str, description: str, payload: str,
                         callback_url: str | None = None) -> dict:
    body = {
        "amount": amount, "numPayments": 1, "currency": currency,
        "description": description[:1000], "payload": payload, "expiredIn": 3600,
    }
    if callback_url:
        body["callbackUrl"] = callback_url
    return await _req("POST", "/tg-invoices", json=body)


async def get_invoice(invoice_id: str) -> dict:
    return await _req("GET", f"/tg-invoices/{invoice_id}")
