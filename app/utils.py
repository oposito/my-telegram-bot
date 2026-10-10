import logging

from aiogram import Bot

from app import config, settings

log = logging.getLogger(__name__)


def admin_ids() -> set[int]:
    return set(config.ADMIN_IDS) | config._ids(settings.get("extra_admins"))


def is_admin(user_id: int) -> bool:
    return user_id in admin_ids()


def money(v: float) -> str:
    v = round(float(v), 2)
    return f"{int(v)}" if v == int(v) else f"{v:.2f}"


def coin_amount(v: float) -> str:
    s = f"{v:.8f}".rstrip("0").rstrip(".")
    return s or "0"


async def notify_admins(bot: Bot, text: str, **kw) -> None:
    for aid in admin_ids():
        try:
            await bot.send_message(aid, text, **kw)
        except Exception as e:  # noqa: BLE001
            log.warning("notify admin %s: %s", aid, e)


def chat_ref(raw: str) -> int | str:
    raw = raw.strip()
    if raw.lstrip("-").isdigit():
        return int(raw)
    if raw.startswith("https://t.me/"):
        raw = "@" + raw.split("/")[-1]
    return raw if raw.startswith("@") else "@" + raw


def extract_emoji(message) -> str | None:
    """Достаёт кастом-эмодзи из сообщения: 'id|символ'."""
    text = message.text or message.caption or ""
    for ent in (message.entities or message.caption_entities or []):
        if ent.type == "custom_emoji":
            return f"{ent.custom_emoji_id}|{ent.extract_from(text) or '⭐'}"
    if message.sticker and message.sticker.custom_emoji_id:
        return f"{message.sticker.custom_emoji_id}|{message.sticker.emoji or '⭐'}"
    if text.strip().isdigit():
        return f"{text.strip()}|⭐"
    return None


def tg_emoji(value: str | None) -> str:
    if not value or "|" not in value:
        return ""
    eid, ch = value.split("|", 1)
    return f'<tg-emoji emoji-id="{eid}">{ch}</tg-emoji> '


async def send_sticker(bot: Bot, chat_id: int, key: str) -> None:
    fid = settings.get(key)
    if not fid:
        return
    try:
        await bot.send_sticker(chat_id, fid)
    except Exception as e:  # noqa: BLE001
        log.warning("sticker %s: %s", key, e)
