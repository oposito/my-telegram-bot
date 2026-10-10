"""Если Telegram не разрешил кастом-эмодзи (нет Premium у владельца бота),
повторяем запрос с обычными эмодзи вместо падения."""
import logging
import re

from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramBadRequest

log = logging.getLogger(__name__)
TAG = re.compile(r"<tg-emoji[^>]*>(.*?)</tg-emoji>", re.S)


def _strip_markup(markup) -> bool:
    changed = False
    rows = getattr(markup, "inline_keyboard", None) or getattr(markup, "keyboard", None) or []
    for row in rows:
        for b in row:
            if getattr(b, "icon_custom_emoji_id", None):
                b.icon_custom_emoji_id = None
                changed = True
    return changed


class EmojiFallback(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        try:
            return await make_request(bot, method)
        except TelegramBadRequest:
            changed = False
            for attr in ("text", "caption"):
                v = getattr(method, attr, None)
                if isinstance(v, str) and "<tg-emoji" in v:
                    setattr(method, attr, TAG.sub(r"\1", v))
                    changed = True
            markup = getattr(method, "reply_markup", None)
            if markup is not None and _strip_markup(markup):
                changed = True
            if not changed:
                raise
            log.warning("Кастом-эмодзи недоступны (нужен Telegram Premium у владельца бота) — отправляю обычные")
            return await make_request(bot, method)
