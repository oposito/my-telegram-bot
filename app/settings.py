"""Настройки, которые администратор меняет прямо в боте (хранятся в БД)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.db import Session, Setting


@dataclass
class Opt:
    key: str
    group: str
    type: str  # str | text | int | float | bool
    default: str
    title: str
    hint: str = ""


OPTIONS: list[Opt] = [
    # --- Основное
    Opt("shop_name", "main", "str", "Digital Shop", "Название магазина"),
    Opt("welcome_ru", "main", "text", "👋 Добро пожаловать в <b>{shop}</b>!\n\nЗдесь можно купить цифровые лицензии с моментальной выдачей.", "Приветствие (RU)", "Можно использовать {shop} и {name}"),
    Opt("welcome_en", "main", "text", "👋 Welcome to <b>{shop}</b>!\n\nBuy digital licenses with instant delivery.", "Приветствие (EN)", "Можно использовать {shop} и {name}"),
    Opt("faq_ru", "main", "text", "❓ <b>FAQ</b>\n\n1. Оплатите товар удобным способом.\n2. Бот сразу выдаст ключ и файл.\n3. Вопросы — в поддержку.", "FAQ / правила (RU)"),
    Opt("faq_en", "main", "text", "❓ <b>FAQ</b>\n\n1. Pay with any method.\n2. The bot instantly sends your key and file.\n3. Questions — contact support.", "FAQ / правила (EN)"),
    Opt("support_contact", "main", "str", "", "Контакт поддержки (@username)", "Пусто — пользователи пишут через бота"),
    Opt("required_channel", "main", "str", "", "Обязательная подписка на канал", "@channel или -100..., бот должен быть админом. «-» — выключить"),
    Opt("required_channel_link", "main", "str", "", "Ссылка на канал подписки", "https://t.me/..."),
    # --- Оплата
    Opt("pay_stars", "pay", "bool", "1", "Оплата Telegram Stars"),
    Opt("pay_crypto", "pay", "bool", "1", "Оплата криптой (xRocket)"),
    Opt("pay_yoomoney", "pay", "bool", "0", "Оплата картой/ЮMoney (авто)"),
    Opt("pay_sbp", "pay", "bool", "1", "СБП по реквизитам (ручная проверка)"),
    Opt("stars_rate", "pay", "float", "1.6", "Курс: сколько ₽ стоит 1 ⭐", "Цена в ⭐ = цена в ₽ / курс"),
    Opt("usdt_rub", "pay", "str", "auto", "Курс USDT в ₽", "auto — брать с биржи, или число, например 90"),
    Opt("crypto_currencies", "pay", "str", "ALL", "Криптовалюты", "ALL — все доступные в xRocket, или список: USDT,GRAM,BTC"),
    Opt("crypto_rates", "pay", "str", "", "Ручные курсы монет (в USDT)", "Например: GRAM=1.5,NOT=0.002. Пусто — авто"),
    Opt("markup_stars", "pay", "float", "0", "Наценка для Stars, %"),
    Opt("markup_crypto", "pay", "float", "0", "Наценка для крипты, %"),
    Opt("markup_yoomoney", "pay", "float", "0", "Наценка для карты/ЮMoney, %"),
    Opt("xrocket_token", "pay", "str", "", "xRocket API токен", "Пусто — берётся из переменной XROCKET_API_KEY"),
    Opt("yoomoney_wallet", "pay", "str", "", "Номер кошелька ЮMoney"),
    Opt("yoomoney_secret", "pay", "str", "", "Секрет HTTP-уведомлений ЮMoney"),
    Opt("sbp_details_ru", "pay", "text", "Переведите сумму по СБП на номер +7XXXXXXXXXX (Банк), затем нажмите «Я оплатил» и пришлите скриншот.", "Реквизиты СБП (RU)"),
    Opt("sbp_details_en", "pay", "text", "Send the amount via SBP to +7XXXXXXXXXX (Bank), then press «I paid» and send a screenshot.", "Реквизиты СБП (EN)"),
    # --- Рефералы и скидки
    Opt("ref_enabled", "ref", "bool", "1", "Реферальная система"),
    Opt("ref_levels", "ref", "str", "10,5,2", "Скидка по уровням, %", "Через запятую: 1-й уровень, 2-й, 3-й..."),
    Opt("ref_each_purchase", "ref", "bool", "1", "Начислять за каждую покупку", "Выкл — только за первую покупку реферала"),
    Opt("ref_newbie_discount", "ref", "float", "0", "Скидка приглашённому на 1-ю покупку, %"),
    Opt("max_discount", "ref", "float", "50", "Максимальная суммарная скидка, %"),
    # --- Отзывы
    Opt("reviews_enabled", "rev", "bool", "1", "Отзывы"),
    Opt("reviews_channel", "rev", "str", "", "Канал для публикации отзывов", "@channel или -100..., бот должен быть админом"),
    Opt("review_bonus", "rev", "float", "0", "Скидка за одобренный отзыв, %"),
    # --- Оформление
    Opt("sticker_welcome", "design", "sticker", "", "Стикер при /start", "Пришлите стикер (можно премиум/анимированный). «-» — убрать"),
    Opt("sticker_purchase", "design", "sticker", "", "Стикер после покупки", "Пришлите стикер. «-» — убрать"),
    Opt("sticker_review", "design", "sticker", "", "Стикер после одобрения отзыва", "Пришлите стикер. «-» — убрать"),
    Opt("sticker_support", "design", "sticker", "", "Стикер к ответу поддержки", "Пришлите стикер. «-» — убрать"),
    # --- Администраторы
    Opt("extra_admins", "adm", "str", "", "Дополнительные админы (ID через запятую)"),
]

GROUPS = {
    "main": "🏠 Основное",
    "pay": "💳 Оплата",
    "ref": "🤝 Рефералы и скидки",
    "rev": "⭐ Отзывы",
    "design": "🖼 Стикеры",
    "adm": "👮 Администраторы",
}

BY_KEY = {o.key: o for o in OPTIONS}
_cache: dict[str, str] = {}


async def load() -> None:
    async with Session() as s:
        rows = (await s.execute(select(Setting))).scalars().all()
    _cache.clear()
    _cache.update({r.key: r.value for r in rows})


def get(key: str) -> str:
    if key in _cache:
        return _cache[key]
    opt = BY_KEY.get(key)
    return opt.default if opt else ""


def get_bool(key: str) -> bool:
    return get(key).strip() in ("1", "true", "yes", "on")


def get_float(key: str, fallback: float = 0.0) -> float:
    try:
        return float(get(key).replace(",", "."))
    except ValueError:
        return fallback


async def put(key: str, value: str) -> None:
    async with Session() as s:
        row = await s.get(Setting, key)
        if row:
            row.value = value
        else:
            s.add(Setting(key=key, value=value))
        await s.commit()
    _cache[key] = value


def ref_levels() -> list[float]:
    out = []
    for p in get("ref_levels").replace(";", ",").split(","):
        try:
            v = float(p.strip().replace("%", ""))
            if v > 0:
                out.append(v)
        except ValueError:
            continue
    return out
