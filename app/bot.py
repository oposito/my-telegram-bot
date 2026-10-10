import asyncio
import datetime as dt
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiohttp import web
from sqlalchemy import select

from app import config, settings
from app.db import Order, Session, init_db, now
from app.handlers import admin, reviews, shop as shop_handlers, user
from app.emoji_fallback import EmojiFallback
from app.middlewares import UserMiddleware
from app.services import http, xrocket
from app.web import build_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")


async def crypto_watcher(bot: Bot) -> None:
    """Каждые 20 секунд проверяет неоплаченные счета xRocket — выдача без нажатия кнопки."""
    while True:
        try:
            if xrocket.token():
                since = now() - dt.timedelta(hours=2)
                async with Session() as s:
                    orders = (await s.execute(select(Order).where(
                        Order.method == "crypto", Order.status == "pending", Order.external_id.is_not(None),
                        Order.created_at >= since))).scalars().all()
                for o in orders:
                    try:
                        await shop_handlers.check_crypto_order(bot, o)
                    except Exception as e:  # noqa: BLE001
                        log.warning("crypto check %s: %s", o.id, e)
                    await asyncio.sleep(0.3)
        except Exception as e:  # noqa: BLE001
            log.exception("crypto watcher: %s", e)
        await asyncio.sleep(20)


async def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit("Не задан BOT_TOKEN (переменная окружения)")
    await init_db()
    await settings.load()

    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    bot.session.middleware(EmojiFallback())
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(UserMiddleware())
    dp.callback_query.outer_middleware(UserMiddleware())
    dp.include_routers(admin.router, shop_handlers.router, reviews.router, user.router)

    await bot.set_my_commands([BotCommand(command="start", description="Главное меню / Main menu"),
                               BotCommand(command="lang", description="Язык / Language")])

    runner = web.AppRunner(build_app(bot))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.PORT).start()
    log.info("HTTP-сервер слушает порт %s", config.PORT)

    watcher = asyncio.create_task(crypto_watcher(bot))
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        watcher.cancel()
        await runner.cleanup()
        await http.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
