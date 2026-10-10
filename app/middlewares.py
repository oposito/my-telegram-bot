import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject

from app import settings
from app.db import Session, User
from app.i18n import t
from app.utils import chat_ref, is_admin

log = logging.getLogger(__name__)


class UserMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user = data.get("event_from_user")
        chat = data.get("event_chat")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)
        # Работаем только в личке (кроме pre_checkout и т.п. без чата)
        if chat is not None and chat.type != "private":
            return None
        async with Session() as s:
            user = await s.get(User, tg_user.id)
            if user is None:
                user = User(id=tg_user.id, username=tg_user.username, first_name=tg_user.first_name)
                s.add(user)
                data["is_new_user"] = True
            else:
                user.username, user.first_name = tg_user.username, tg_user.first_name
                if user.blocked_bot:
                    user.blocked_bot = False
            await s.commit()
        data["user"] = user
        data["lang"] = user.lang or "ru"
        admin = is_admin(user.id)
        data["is_admin"] = admin
        if isinstance(event, Message) and event.successful_payment:
            return await handler(event, data)  # платёж обрабатываем всегда

        if user.banned and not admin:
            if isinstance(event, Message):
                await event.answer(t("banned", user.lang))
            elif isinstance(event, CallbackQuery):
                await event.answer(t("banned", user.lang), show_alert=True)
            return None

        channel = settings.get("required_channel").strip()
        if channel and channel != "-" and not admin and user.lang:
            is_check = isinstance(event, CallbackQuery) and event.data == "sub:check"
            if not await is_subscribed(data["bot"], channel, user.id):
                if isinstance(event, CallbackQuery):
                    await event.answer(t("not_subscribed", user.lang), show_alert=is_check)
                    if not is_check:
                        await send_sub_prompt(event.message, user.lang, channel)
                elif isinstance(event, Message):
                    await send_sub_prompt(event, user.lang, channel)
                return None
        return await handler(event, data)


async def is_subscribed(bot: Bot, channel: str, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_ref(channel), user_id)
        return m.status not in ("left", "kicked")
    except Exception as e:  # noqa: BLE001
        log.warning("subscription check failed (бот админ в канале?): %s", e)
        return True


async def send_sub_prompt(message: Message | None, lang: str, channel: str) -> None:
    if message is None:
        return
    link = settings.get("required_channel_link").strip()
    if not link and channel.startswith("@"):
        link = f"https://t.me/{channel[1:]}"
    from app.keyboards import bt, ikb
    rows = []
    if link:
        rows.append([bt("btn_subscribe", lang, link)])
    rows.append([bt("btn_check_sub", lang, "sub:check")])
    await message.answer(t("need_sub", lang), reply_markup=ikb(rows))
