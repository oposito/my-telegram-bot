"""Ядро магазина: цены, скидки, заказы, выдача, рефералы."""
from __future__ import annotations

import html
import logging
import math

from aiogram import Bot
from sqlalchemy import func, select, update

from app import settings
from app.db import Key, Order, Product, Promo, PromoUse, Session, User, now
from app.i18n import t
from app.keyboards import bt, ikb
from app.services import rates
from app.utils import coin_amount, money, notify_admins, send_sticker

log = logging.getLogger(__name__)


async def stock(product: Product) -> int | None:
    """None — без ограничений (товар без ключей)."""
    if not product.use_keys:
        return None
    async with Session() as s:
        return await s.scalar(select(func.count(Key.id)).where(Key.product_id == product.id, Key.sold.is_(False)))


async def validate_promo(code: str, user_id: int) -> Promo | None:
    code = code.strip().upper()
    async with Session() as s:
        p = await s.get(Promo, code)
        if not p or not p.active:
            return None
        if p.expires_at and p.expires_at < now():
            return None
        if p.max_uses and p.used >= p.max_uses:
            return None
        used = await s.scalar(select(PromoUse.id).where(PromoUse.code == code, PromoUse.user_id == user_id))
        return None if used else p


async def _has_purchases(user_id: int) -> bool:
    async with Session() as s:
        return bool(await s.scalar(select(func.count(Order.id)).where(
            Order.user_id == user_id, Order.status.in_(("delivered", "waiting")))))


async def discount_for(user: User, promo_percent: float = 0) -> tuple[float, float]:
    """Возвращает (итоговая скидка %, сколько из неё — накопленная реферальная скидка)."""
    max_d = max(0.0, min(100.0, settings.get_float("max_discount", 50)))
    newbie = 0.0
    if user.referrer_id and settings.get_bool("ref_enabled") and not await _has_purchases(user.id):
        newbie = settings.get_float("ref_newbie_discount")
    # промокод может давать любую скидку (вплоть до 100%), а накопленные бонусы ограничены max_discount
    base = min(100.0, promo_percent + min(newbie, max_d))
    cap = max(max_d, promo_percent)
    ref_used = max(0.0, min(user.ref_discount or 0, cap - base))
    return round(min(100.0, base + ref_used), 2), round(ref_used, 2)


def apply(value: float, discount: float, markup: float = 0) -> float:
    return value * (1 - discount / 100) * (1 + markup / 100)


def price_rub(product: Product, discount: float) -> float:
    return round(apply(product.price_rub, discount), 2)


def price_stars(product: Product, discount: float) -> int:
    base = product.price_stars or (product.price_rub / max(settings.get_float("stars_rate", 1.6), 0.01))
    return max(1, math.ceil(apply(base, discount, settings.get_float("markup_stars"))))


def price_yoomoney(product: Product, discount: float) -> float:
    return round(apply(product.price_rub, discount, settings.get_float("markup_yoomoney")), 2)


async def price_usdt(product: Product, discount: float) -> float:
    base = product.price_usdt or (product.price_rub / await rates.usdt_rub())
    return apply(base, discount, settings.get_float("markup_crypto"))


async def create_order(user: User, product: Product, method: str, discount: float, ref_used: float,
                       promo: str | None, pay_amount: float, pay_currency: str) -> Order:
    async with Session() as s:
        o = Order(user_id=user.id, product_id=product.id, method=method, discount=discount,
                  ref_used=ref_used, promo_code=promo, amount_rub=price_rub(product, discount),
                  pay_amount=pay_amount, pay_currency=pay_currency)
        s.add(o)
        await s.commit()
        await s.refresh(o)
        return o


async def set_order(order_id: int, **values) -> None:
    async with Session() as s:
        await s.execute(update(Order).where(Order.id == order_id).values(**values))
        await s.commit()


async def _take_key(order_id: int, product_id: int) -> Key | None:
    async with Session() as s:
        for _ in range(5):
            kid = await s.scalar(select(Key.id).where(Key.product_id == product_id, Key.sold.is_(False))
                                 .order_by(Key.id).limit(1))
            if kid is None:
                return None
            res = await s.execute(update(Key).where(Key.id == kid, Key.sold.is_(False))
                                  .values(sold=True, order_id=order_id))
            await s.commit()
            if res.rowcount:
                return await s.get(Key, kid)
    return None


def duration_text(days: int | None, lang: str) -> str:
    return t("forever", lang) if not days else t("days", lang, n=days)


def file_for(product: Product) -> tuple[str | None, str | None]:
    if not product.deliver_file:
        return None, None
    if product.file_id:
        return product.file_id, product.file_name
    fid = settings.get("main_file_id")
    return (fid or None), settings.get("main_file_name") or None


async def send_file(bot: Bot, chat_id: int, product: Product, caption: str | None = None) -> bool:
    fid, _ = file_for(product)
    if not fid:
        return False
    await bot.send_document(chat_id, fid, caption=caption)
    return True


async def fulfill(bot: Bot, order_id: int, allowed=("pending",)) -> bool:
    """Отмечает заказ оплаченным и выдаёт товар. Безопасно вызывать повторно."""
    async with Session() as s:
        res = await s.execute(update(Order).where(Order.id == order_id, Order.status.in_(allowed))
                              .values(status="paid", paid_at=now()))
        await s.commit()
        if not res.rowcount:
            return False
        order = await s.get(Order, order_id)
        product = await s.get(Product, order.product_id)
        user = await s.get(User, order.user_id)
    return await _deliver(bot, order, product, user, first_time=("waiting" not in allowed))


async def _deliver(bot: Bot, order: Order, product: Product, user: User, first_time: bool = True) -> bool:
    lang = user.lang or "ru"
    key = None
    if product is None:
        await set_order(order.id, status="waiting")
        return False
    if product.use_keys:
        key = await _take_key(order.id, product.id)
        if not key:
            await set_order(order.id, status="waiting")
            if first_time:
                await _consume_discounts(order, user)
                await _safe_send(bot, user.id, t("waiting_key", lang))
                await notify_admins(bot, f"⚠️ Заказ №{order.id} оплачен, но ключи для «{product.name_ru}» закончились! "
                                         f"Добавьте ключи — выдача произойдёт автоматически.")
            return False
    await set_order(order.id, status="delivered", key_id=key.id if key else None)
    if first_time:
        await _consume_discounts(order, user)

    kb = None
    if settings.get_bool("reviews_enabled"):
        kb = ikb([[bt("btn_leave_review", lang, f"rev:new:{order.id}")]])
    text = t("delivered", lang, order=order.id, name=product.name(lang))
    if key:
        text += "\n\n" + t("your_key", lang, key=html.escape(key.value), dur=duration_text(key.duration_days, lang))
    await send_sticker(bot, user.id, "sticker_purchase")
    await _safe_send(bot, user.id, text, reply_markup=kb)
    try:
        await send_file(bot, user.id, product)
    except Exception as e:  # noqa: BLE001
        log.warning("send file: %s", e)

    if first_time:
        await _referral_bonus(bot, user)
    await notify_admins(bot, f"💰 Продажа! Заказ №{order.id}\n{product.name_ru}\n"
                             f"Покупатель: <code>{user.id}</code> @{user.username or '-'}\n"
                             f"Оплата: {order.method} — {coin_amount(order.pay_amount)} {order.pay_currency}"
                             + (f"\nКлюч: <code>{key.value}</code>" if key else ""))
    return True


async def _consume_discounts(order: Order, user: User) -> None:
    async with Session() as s:
        if order.ref_used:
            u = await s.get(User, user.id)
            u.ref_discount = max(0.0, round((u.ref_discount or 0) - order.ref_used, 2))
        if order.promo_code:
            p = await s.get(Promo, order.promo_code)
            if p:
                p.used += 1
                s.add(PromoUse(code=order.promo_code, user_id=user.id))
        try:
            await s.commit()
        except Exception as e:  # noqa: BLE001  (повторное использование промокода)
            log.warning("consume discounts: %s", e)
            await s.rollback()


async def _referral_bonus(bot: Bot, buyer: User) -> None:
    if not settings.get_bool("ref_enabled") or not buyer.referrer_id:
        return
    if not settings.get_bool("ref_each_purchase"):
        async with Session() as s:
            n = await s.scalar(select(func.count(Order.id)).where(
                Order.user_id == buyer.id, Order.status.in_(("delivered", "waiting"))))
        if n and n > 1:
            return
    max_d = settings.get_float("max_discount", 50)
    current_id = buyer.referrer_id
    seen = {buyer.id}
    for lvl, pct in enumerate(settings.ref_levels(), start=1):
        if not current_id or current_id in seen:
            break
        seen.add(current_id)
        async with Session() as s:
            ref = await s.get(User, current_id)
            if not ref:
                break
            ref.ref_discount = round(min(max_d, (ref.ref_discount or 0) + pct), 2)
            await s.commit()
            disc, lang, next_id = ref.ref_discount, ref.lang, ref.referrer_id
        await _safe_send(bot, current_id, t("ref_bonus", lang, lvl=lvl, p=money(pct), disc=money(disc)))
        current_id = next_id


async def add_discount(user_id: int, pct: float) -> float:
    async with Session() as s:
        u = await s.get(User, user_id)
        if not u:
            return 0
        u.ref_discount = round(min(settings.get_float("max_discount", 50), max(0.0, (u.ref_discount or 0) + pct)), 2)
        await s.commit()
        return u.ref_discount


async def process_waiting(bot: Bot, product_id: int) -> int:
    async with Session() as s:
        ids = (await s.execute(select(Order.id).where(Order.product_id == product_id, Order.status == "waiting")
                               .order_by(Order.id))).scalars().all()
    done = 0
    for oid in ids:
        if await fulfill(bot, oid, allowed=("waiting",)):
            done += 1
    return done


async def _safe_send(bot: Bot, chat_id: int, text: str, **kw) -> None:
    try:
        await bot.send_message(chat_id, text, **kw)
    except Exception as e:  # noqa: BLE001
        log.warning("send to %s: %s", chat_id, e)


async def deliver_manual(bot: Bot, order_id: int, admin_msg) -> bool:
    """Ручная выдача: админ сам отправляет ключ/файл/текст, бот пересылает его покупателю."""
    async with Session() as s:
        before = await s.get(Order, order_id)
        if not before or before.status not in ("pending", "waiting"):
            return False
        was_waiting = before.status == "waiting"
        res = await s.execute(update(Order).where(Order.id == order_id, Order.status == before.status)
                              .values(status="delivered", paid_at=now()))
        await s.commit()
        if not res.rowcount:
            return False
        order = await s.get(Order, order_id)
        product = await s.get(Product, order.product_id)
        user = await s.get(User, order.user_id)
    lang = user.lang or "ru"
    if not was_waiting:
        await _consume_discounts(order, user)
    await send_sticker(bot, user.id, "sticker_purchase")
    kb = ikb([[bt("btn_leave_review", lang, f"rev:new:{order.id}")]]) if settings.get_bool("reviews_enabled") else None
    await _safe_send(bot, user.id, t("delivered", lang, order=order.id, name=product.name(lang) if product else "—"))
    try:
        await admin_msg.copy_to(user.id, reply_markup=kb)
    except Exception as e:  # noqa: BLE001
        log.warning("manual copy: %s", e)
        return False
    if not was_waiting:
        await _referral_bonus(bot, user)
    return True
