from aiogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app import settings
from app.i18n import button_text, icon, t


def kb_btn(key: str, lang: str) -> KeyboardButton:
    return KeyboardButton(text=button_text(key, lang), icon_custom_emoji_id=icon(key))


def main_menu(lang: str, admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [kb_btn("btn_catalog", lang)],
        [kb_btn("btn_profile", lang), kb_btn("btn_purchases", lang)],
    ]
    row = []
    if settings.get_bool("reviews_enabled"):
        row.append(kb_btn("btn_reviews", lang))
    if settings.get_bool("ref_enabled"):
        row.append(kb_btn("btn_ref", lang))
    if row:
        rows.append(row)
    rows.append([kb_btn("btn_support", lang), kb_btn("btn_faq", lang), kb_btn("btn_lang", lang)])
    if admin:
        rows.append([kb_btn("btn_admin", lang)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text="🇷🇺 Русский", callback_data="lang:ru"),
                                                  B(text="🇬🇧 English", callback_data="lang:en")]])


def bt(key: str, lang: str, val: str, **kw) -> tuple:
    """Кнопка из текста бота с кастом-эмодзи (если задан в «Оформлении»)."""
    return (button_text(key, lang, **kw), val, icon(key))


def ikb(rows: list[list[tuple]]) -> InlineKeyboardMarkup:
    """rows: [[(text, callback_or_url[, custom_emoji_id]), ...], ...]; значения с http — ссылки."""
    out = []
    for row in rows:
        r = []
        for item in row:
            text, val = item[0], item[1]
            ic = item[2] if len(item) > 2 else None
            if val.startswith(("http://", "https://", "tg://")):
                r.append(B(text=text, url=val, icon_custom_emoji_id=ic))
            else:
                r.append(B(text=text, callback_data=val, icon_custom_emoji_id=ic))
        out.append(r)
    return InlineKeyboardMarkup(inline_keyboard=out)


def cancel_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return ikb([[bt("btn_cancel", lang, "cancel")]])
