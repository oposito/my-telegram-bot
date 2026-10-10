import html
import logging
import math

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy import select

from app import settings
from app.db import Order, Product, Session, User
from app.i18n import all_variants, btn, t, button_text, icon
from app.keyboards import bt, cancel_kb, ikb
from app.services import rates, shop, xrocket, yoomoney
from app.utils import admin_ids, coin_amount, money, tg_emoji

log = logging.getLogger(__name__)
router = Router(name="shop")
POPULAR = ["USDT", "GRAM", "BTC", "ETH", "USDC", "TRX", "SOL", "BNB", "NOT", "DOGS"]
PAGE = 24


class Buy(StatesGroup):
    promo = State()
    receipt = State()


async def _fresh_user(uid: int) -> User:
    async with Session() as s:
        return await s.get(User, uid)


async def _promo(state: FSMContext, uid: int) -> tuple[str | None, float]:
    data = await state.get_data()
    code = data.get("promo")
    if not code:
        return None, 0
    p = await shop.validate_promo(code, uid)
    if not p:
        await state.update_data(promo=None)
        return None, 0
    return p.code, p.percent


# ---------- Каталог ----------
async def catalog_markup(lang: str):
    async with Session() as s:
        items = (await s.execute(select(Product).where(Product.active.is_(True))
                                 .order_by(Product.sort, Product.id))).scalars().all()
    return items, ikb([[(f"{p.name(lang)} — {money(p.price_rub)} ₽", f"p:{p.id}",
                         p.icon.split("|")[0] if p.icon else None)] for p in items])


@router.message(btn("btn_catalog"))
async def catalog(message: Message, lang: str, state: FSMContext) -> None:
    await state.set_state(None)
    items, kb = await catalog_markup(lang)
    if not items:
        await message.answer(t("catalog_empty", lang))
        return
    await message.answer(t("catalog_title", lang), reply_markup=kb)


@router.callback_query(F.data == "cat")
async def catalog_cb(cb: CallbackQuery, lang: str) -> None:
    items, kb = await catalog_markup(lang)
    await cb.message.edit_text(t("catalog_title", lang) if items else t("catalog_empty", lang), reply_markup=kb)
    await cb.answer()


async def product_text(p: Product, user: User, lang: str, state: FSMContext) -> str:
    st = await shop.stock(p)
    stock_s = t("stock_unlimited", lang) if st is None else str(st)
    text = t("product_card", lang, name=tg_emoji(p.icon) + html.escape(p.name(lang)), desc=p.desc(lang),
             price=f"{money(p.price_rub)} ₽", stock=stock_s)
    code, pct = await _promo(state, user.id)
    disc, _ = await shop.discount_for(user, pct)
    if disc:
        text += "\n" + t("your_discount", lang, d=money(disc), price=f"{money(shop.price_rub(p, disc))} ₽")
    if code:
        text += "\n" + t("promo_ok", lang, p=money(pct)) + f" ({code})"
    return text


def product_kb(pid: int, lang: str):
    return ikb([[bt("btn_buy", lang, f"buy:{pid}")], [bt("btn_promo", lang, f"promo:{pid}")],
                [bt("btn_back", lang, "cat")]])


@router.callback_query(F.data.startswith("p:"))
async def product(cb: CallbackQuery, lang: str, state: FSMContext) -> None:
    pid = int(cb.data.split(":")[1])
    async with Session() as s:
        p = await s.get(Product, pid)
    if not p or not p.active:
        await cb.answer(t("out_of_stock", lang), show_alert=True)
        return
    user = await _fresh_user(cb.from_user.id)
    await cb.message.edit_text(await product_text(p, user, lang, state), reply_markup=product_kb(pid, lang),
                               disable_web_page_preview=True)
    await cb.answer()


@router.callback_query(F.data.startswith("promo:"))
async def promo_ask(cb: CallbackQuery, lang: str, state: FSMContext) -> None:
    await state.set_state(Buy.promo)
    await state.update_data(promo_pid=int(cb.data.split(":")[1]))
    await cb.message.answer(t("enter_promo", lang), reply_markup=cancel_kb(lang))
    await cb.answer()


@router.message(Buy.promo, F.text)
async def promo_get(message: Message, lang: str, state: FSMContext) -> None:
    p = await shop.validate_promo(message.text, message.from_user.id)
    data = await state.get_data()
    await state.set_state(None)
    if not p:
        await message.answer(t("promo_bad", lang))
        return
    await state.update_data(promo=p.code)
    await message.answer(t("promo_ok", lang, p=money(p.percent)))
    async with Session() as s:
        prod = await s.get(Product, data.get("promo_pid") or 0)
    if prod:
        user = await _fresh_user(message.from_user.id)
        await message.answer(await product_text(prod, user, lang, state), reply_markup=product_kb(prod.id, lang))


# ---------- Покупка ----------
async def _prepare(cb: CallbackQuery, state: FSMContext, lang: str):
    pid = int(cb.data.split(":")[-1])
    async with Session() as s:
        p = await s.get(Product, pid)
    if not p or not p.active:
        await cb.answer(t("out_of_stock", lang), show_alert=True)
        return None
    st = await shop.stock(p)
    if st is not None and st <= 0:
        await cb.answer(t("out_of_stock", lang), show_alert=True)
        return None
    user = await _fresh_user(cb.from_user.id)
    code, pct = await _promo(state, user.id)
    disc, ref_used = await shop.discount_for(user, pct)
    return p, user, code, disc, ref_used


@router.callback_query(F.data.startswith("buy:"))
async def buy(cb: CallbackQuery, lang: str, state: FSMContext, bot: Bot) -> None:
    prep = await _prepare(cb, state, lang)
    if not prep:
        return
    p, user, code, disc, ref_used = prep
    if shop.price_rub(p, disc) <= 0:
        o = await shop.create_order(user, p, "free", disc, ref_used, code, 0, "RUB")
        await cb.answer()
        await shop.fulfill(bot, o.id)
        return
    rows = []
    if settings.get_bool("pay_stars"):
        rows.append([bt("m_stars", lang, f"pay:stars:{p.id}", v=shop.price_stars(p, disc))])
    if xrocket.enabled():
        rows.append([bt("m_crypto", lang, f"pay:crypto:{p.id}")])
    if yoomoney.enabled():
        rows.append([bt("m_yoomoney", lang, f"pay:ym:{p.id}", v=money(shop.price_yoomoney(p, disc)))])
    if settings.get_bool("pay_sbp"):
        rows.append([bt("m_sbp", lang, f"pay:sbp:{p.id}", v=money(shop.price_rub(p, disc)))])
    if not rows:
        await cb.answer(t("no_methods", lang), show_alert=True)
        return
    rows.append([bt("btn_back", lang, f"p:{p.id}")])
    await cb.message.edit_text(t("choose_method", lang, price=f"{money(shop.price_rub(p, disc))} ₽", d=money(disc)),
                               reply_markup=ikb(rows))
    await cb.answer()


@router.callback_query(F.data.startswith("pay:stars:"))
async def pay_stars(cb: CallbackQuery, lang: str, state: FSMContext, bot: Bot) -> None:
    prep = await _prepare(cb, state, lang)
    if not prep or not settings.get_bool("pay_stars"):
        return
    p, user, code, disc, ref_used = prep
    stars = shop.price_stars(p, disc)
    o = await shop.create_order(user, p, "stars", disc, ref_used, code, stars, "XTR")
    await bot.send_invoice(cb.from_user.id, title=p.name(lang)[:32], description=(p.desc(lang) or p.name(lang))[:255],
                           payload=f"order:{o.id}", currency="XTR",
                           prices=[LabeledPrice(label=p.name(lang)[:32], amount=stars)])
    await cb.answer()


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery) -> None:
    ok = False
    if q.invoice_payload.startswith("order:"):
        async with Session() as s:
            o = await s.get(Order, int(q.invoice_payload.split(":")[1]))
        ok = bool(o and o.status == "pending" and o.user_id == q.from_user.id and int(o.pay_amount) == q.total_amount)
    await q.answer(ok=ok, error_message=None if ok else "Order expired, please create a new one")


@router.message(F.successful_payment)
async def paid_stars(message: Message, bot: Bot) -> None:
    sp = message.successful_payment
    if not sp.invoice_payload.startswith("order:"):
        return
    oid = int(sp.invoice_payload.split(":")[1])
    await shop.set_order(oid, charge_id=sp.telegram_payment_charge_id)
    await shop.fulfill(bot, oid)


# ---------- Крипта ----------
async def _coins_sorted() -> list[str]:
    coins = [c["currency"] for c in await xrocket.allowed_coins()]
    pop = [c for c in POPULAR if c in coins]
    return pop + sorted(c for c in coins if c not in pop)


@router.callback_query(F.data.startswith("pay:crypto:"))
async def pay_crypto(cb: CallbackQuery, lang: str, state: FSMContext) -> None:
    await _coin_page(cb, lang, int(cb.data.split(":")[2]), 0)


@router.callback_query(F.data.startswith("coinpg:"))
async def coin_page(cb: CallbackQuery, lang: str) -> None:
    _, pid, page = cb.data.split(":")
    await _coin_page(cb, lang, int(pid), int(page))


async def _coin_page(cb: CallbackQuery, lang: str, pid: int, page: int) -> None:
    try:
        coins = await _coins_sorted()
    except Exception as e:  # noqa: BLE001
        log.warning("xrocket coins: %s", e)
        await cb.answer(t("pay_error", lang), show_alert=True)
        return
    chunk = coins[page * PAGE:(page + 1) * PAGE]
    rows = [[(c, f"coin:{pid}:{c}") for c in chunk[i:i + 3]] for i in range(0, len(chunk), 3)]
    nav = []
    if page > 0:
        nav.append(("◀️", f"coinpg:{pid}:{page - 1}"))
    if (page + 1) * PAGE < len(coins):
        nav.append(("▶️", f"coinpg:{pid}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([bt("btn_back", lang, f"buy:{pid}")])
    await cb.message.edit_text(t("choose_coin", lang), reply_markup=ikb(rows))
    await cb.answer()


@router.callback_query(F.data.startswith("coin:"))
async def pay_coin(cb: CallbackQuery, lang: str, state: FSMContext, bot: Bot) -> None:
    cur = cb.data.split(":")[2]
    pid = int(cb.data.split(":")[1])
    async with Session() as s:
        p = await s.get(Product, pid)
    if not p or not p.active or not xrocket.enabled():
        await cb.answer(t("out_of_stock", lang), show_alert=True)
        return
    st = await shop.stock(p)
    if st is not None and st <= 0:
        await cb.answer(t("out_of_stock", lang), show_alert=True)
        return
    user = await _fresh_user(cb.from_user.id)
    code, pct = await _promo(state, user.id)
    disc, ref_used = await shop.discount_for(user, pct)
    rate = await rates.coin_usdt(cur)
    if not rate:
        await cb.answer("Курс этой монеты недоступен, выберите другую / Rate unavailable", show_alert=True)
        return
    usdt = await shop.price_usdt(p, disc)
    amount = math.ceil(usdt / rate * 1e8) / 1e8
    coin = next((c for c in await xrocket.coins() if c["currency"] == cur), {})
    amount = max(amount, float(coin.get("minInvoice") or 0))
    o = await shop.create_order(user, p, "crypto", disc, ref_used, code, amount, cur)
    try:
        me = await bot.me()
        inv = await xrocket.create_invoice(amount, cur, f"{p.name(lang)} #{o.id}", f"order:{o.id}",
                                           callback_url=f"https://t.me/{me.username}")
    except Exception as e:  # noqa: BLE001
        log.warning("xrocket invoice: %s", e)
        await shop.set_order(o.id, status="cancelled")
        await cb.answer(t("pay_error", lang), show_alert=True)
        return
    await shop.set_order(o.id, external_id=str(inv["id"]), pay_url=inv.get("link"))
    await cb.message.edit_text(t("pay_crypto", lang, amount=coin_amount(amount), cur=cur),
                               reply_markup=ikb([[bt("btn_pay", lang, inv["link"])],
                                                 [bt("btn_check", lang, f"chk:{o.id}")]]))
    await cb.answer()


async def check_crypto_order(bot: Bot, order: Order) -> str:
    inv = await xrocket.get_invoice(order.external_id)
    status = inv.get("status")
    if status == "paid":
        await shop.fulfill(bot, order.id)
    elif status == "expired":
        await shop.set_order(order.id, status="cancelled")
    return status or ""


@router.callback_query(F.data.startswith("chk:"))
async def check_payment(cb: CallbackQuery, lang: str, bot: Bot) -> None:
    oid = int(cb.data.split(":")[1])
    async with Session() as s:
        o = await s.get(Order, oid)
    if not o or o.user_id != cb.from_user.id:
        await cb.answer()
        return
    if o.status in ("delivered", "waiting", "paid"):
        await cb.answer("✅")
        return
    try:
        status = await check_crypto_order(bot, o) if o.external_id else ""
    except Exception as e:  # noqa: BLE001
        log.warning("check: %s", e)
        status = ""
    if status == "paid":
        await cb.answer("✅")
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:  # noqa: BLE001
            pass
    else:
        await cb.answer(t("not_paid", lang), show_alert=True)


# ---------- ЮMoney ----------
@router.callback_query(F.data.startswith("pay:ym:"))
async def pay_ym(cb: CallbackQuery, lang: str, state: FSMContext, bot: Bot) -> None:
    prep = await _prepare(cb, state, lang)
    if not prep or not yoomoney.enabled():
        return
    p, user, code, disc, ref_used = prep
    amount = shop.price_yoomoney(p, disc)
    o = await shop.create_order(user, p, "yoomoney", disc, ref_used, code, amount, "RUB")
    me = await bot.me()
    url = yoomoney.pay_url(o.id, amount, f"{p.name_ru} #{o.id}", f"https://t.me/{me.username}")
    await shop.set_order(o.id, pay_url=url)
    await cb.message.edit_text(t("pay_yoomoney", lang, amount=money(amount)),
                               reply_markup=ikb([[bt("btn_pay", lang, url)]]))
    await cb.answer()


# ---------- СБП (ручная проверка) ----------
@router.callback_query(F.data.startswith("pay:sbp:"))
async def pay_sbp(cb: CallbackQuery, lang: str, state: FSMContext) -> None:
    prep = await _prepare(cb, state, lang)
    if not prep or not settings.get_bool("pay_sbp"):
        return
    p, user, code, disc, ref_used = prep
    amount = shop.price_rub(p, disc)
    o = await shop.create_order(user, p, "sbp", disc, ref_used, code, amount, "RUB")
    details = settings.get(f"sbp_details_{lang}") or settings.get("sbp_details_ru")
    await cb.message.edit_text(t("sbp_info", lang, amount=money(amount), details=details, order=o.id),
                               reply_markup=ikb([[bt("btn_i_paid", lang, f"sbppaid:{o.id}")]]))
    await cb.answer()


@router.callback_query(F.data.startswith("sbppaid:"))
async def sbp_paid(cb: CallbackQuery, lang: str, state: FSMContext) -> None:
    await state.set_state(Buy.receipt)
    await state.update_data(receipt_order=int(cb.data.split(":")[1]))
    await cb.message.answer(t("send_receipt", lang), reply_markup=cancel_kb(lang))
    await cb.answer()


@router.message(Buy.receipt)
async def sbp_receipt(message: Message, lang: str, state: FSMContext, bot: Bot, user: User) -> None:
    data = await state.get_data()
    await state.set_state(None)
    oid = data.get("receipt_order")
    async with Session() as s:
        o = await s.get(Order, oid or 0)
        p = await s.get(Product, o.product_id) if o else None
    if not o or o.user_id != user.id or o.status != "pending":
        return
    fid = message.photo[-1].file_id if message.photo else (message.document.file_id if message.document else None)
    await shop.set_order(o.id, receipt_file_id=fid)
    kb = ikb([[("✅ Подтвердить и выдать автоматически", f"adm:sbpok:{o.id}")],
              [("✍️ Выдать вручную", f"adm:sbpman:{o.id}"), ("❌ Отклонить", f"adm:sbpno:{o.id}")]])
    head = (f"🏦 СБП: заказ №{o.id}\n{p.name_ru if p else '-'}\nСумма: <b>{money(o.pay_amount)} ₽</b>\n"
            f"Покупатель: <code>{user.id}</code> @{html.escape(user.username or '-')}")
    for aid in admin_ids():
        try:
            await bot.send_message(aid, head)
            await message.copy_to(aid, reply_markup=kb)
        except Exception:  # noqa: BLE001
            pass
    await message.answer(t("receipt_sent", lang))
