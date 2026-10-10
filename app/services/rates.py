"""Курсы валют для автоконвертации цен."""
import logging
import time

from app import settings
from app.services.http import session

log = logging.getLogger(__name__)
_cache: dict[str, tuple[float, float]] = {}
TTL = 600
STABLE = {"USDT", "USDC"}
ALIASES = {"GRAM": ["GRAM", "TON"], "tsTON": ["TON", "GRAM"], "1MBABYDOGE": []}


def _cached(key: str):
    v = _cache.get(key)
    if v and time.time() - v[1] < TTL:
        return v[0]
    return None


async def _gate(symbol: str) -> float | None:
    try:
        async with session().get("https://api.gateio.ws/api/v4/spot/tickers",
                                 params={"currency_pair": f"{symbol}_USDT"}) as r:
            data = await r.json(content_type=None)
            if isinstance(data, list) and data and float(data[0].get("last") or 0) > 0:
                return float(data[0]["last"])
    except Exception as e:  # noqa: BLE001
        log.debug("gate %s: %s", symbol, e)
    return None


async def _okx(symbol: str) -> float | None:
    try:
        async with session().get("https://www.okx.com/api/v5/market/ticker",
                                 params={"instId": f"{symbol}-USDT"}) as r:
            data = await r.json(content_type=None)
            items = data.get("data") or []
            if items and float(items[0].get("last") or 0) > 0:
                return float(items[0]["last"])
    except Exception as e:  # noqa: BLE001
        log.debug("okx %s: %s", symbol, e)
    return None


def _overrides() -> dict[str, float]:
    out = {}
    for part in settings.get("crypto_rates").replace(";", ",").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            try:
                out[k.strip().upper()] = float(v.strip().replace(",", "."))
            except ValueError:
                pass
    return out


async def coin_usdt(currency: str) -> float | None:
    """Цена 1 монеты в USDT."""
    ov = _overrides()
    if currency.upper() in ov:
        return ov[currency.upper()]
    if currency.upper() in STABLE:
        return 1.0
    hit = _cached("c:" + currency)
    if hit:
        return hit
    for sym in ALIASES.get(currency, [currency.upper()]):
        price = await _gate(sym) or await _okx(sym)
        if price:
            _cache["c:" + currency] = (price, time.time())
            return price
    return None


async def usdt_rub() -> float:
    raw = settings.get("usdt_rub").strip().replace(",", ".")
    try:
        if raw and raw.lower() != "auto":
            return float(raw)
    except ValueError:
        pass
    hit = _cached("usdt_rub")
    if hit:
        return hit
    rate = None
    try:
        async with session().get("https://api.coingecko.com/api/v3/simple/price",
                                 params={"ids": "tether", "vs_currencies": "rub"}) as r:
            rate = float((await r.json(content_type=None))["tether"]["rub"])
    except Exception as e:  # noqa: BLE001
        log.warning("coingecko usdt/rub: %s", e)
    if not rate:
        old = _cache.get("usdt_rub")
        rate = old[0] if old else 90.0
    _cache["usdt_rub"] = (rate, time.time())
    return rate
