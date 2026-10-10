"""HTTP-сервер: проверка здоровья для хостинга + уведомления ЮMoney."""
import logging

from aiogram import Bot
from aiohttp import web

from app.db import Order, Session
from app.services import shop, yoomoney

log = logging.getLogger(__name__)


def build_app(bot: Bot) -> web.Application:
    app = web.Application()

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="OK")

    async def ym_notify(request: web.Request) -> web.Response:
        data = dict(await request.post())
        if not yoomoney.check_notification(data):
            log.warning("YooMoney: неверная подпись")
            return web.Response(status=400, text="bad hash")
        if data.get("codepro") == "true" or data.get("unaccepted") == "true":
            return web.Response(text="ignored")
        label = data.get("label", "")
        if not label.startswith("order:"):
            return web.Response(text="no order")
        oid = int(label.split(":")[1])
        async with Session() as s:
            o = await s.get(Order, oid)
        if not o or o.method != "yoomoney":
            return web.Response(text="unknown order")
        paid = float(data.get("withdraw_amount") or data.get("amount") or 0)
        if paid + 0.01 < o.pay_amount:
            log.warning("YooMoney: недоплата по заказу %s: %s < %s", oid, paid, o.pay_amount)
            return web.Response(text="underpaid")
        await shop.set_order(oid, external_id=data.get("operation_id"))
        await shop.fulfill(bot, oid)
        return web.Response(text="OK")

    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_post("/yoomoney", ym_notify)
    return app
