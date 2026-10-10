import html

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from app import settings
from app.db import Order, Product, Session, User
from app.i18n import all_variants, btn, t, button_text, icon
from app.keyboards import bt, cancel_kb, ikb, lang_kb, main_menu
from app.services import shop
from app.utils import admin_ids, money, send_sticker

router = Router(name="user")


class Support(StatesGroup):
    text = State()


async def show_welcome(message: Message, user: User, admin: bool) -> None:
    lang = user.lang or "ru"
    await send_sticker(message.bot, message.chat.id, "sticker_welcome")
    text = settings.get(f"welcome_{lang}") or settings.get("welcome_ru")
    try:
        text = text.format(shop=settings.get("shop_name"), name=html.escape(user.first_name or ""))
    except (KeyError, IndexError, ValueError):
        pass
    await message.answer(text, reply_markup=main_menu(lang, admin))


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, user: User, is_admin: bool,
                    state: FSMContext, is_new_user: bool = False) -> None:
    await state.clear()
    arg = (command.args or "").strip()
    if is_new_user and arg.startswith("ref_") and settings.get_bool("ref_enabled"):
        ref_id = arg[4:]
        if ref_id.isdigit() and int(ref_id) != user.id:
            async with Session() as s:
                ref = await s.get(User, int(ref_id))
                me = await s.get(User, user.id)
                if ref and me and not me.referrer_id:
                    me.referrer_id = ref.id
                    user.referrer_id = ref.id
                    await s.commit()
    if not user.lang:
        await message.answer(t("choose_lang"), reply_markup=lang_kb())
        return
    await show_welcome(message, user, is_admin)


@router.callback_query(F.data.startswith("lang:"))
async def set_lang(cb: CallbackQuery, user: User, is_admin: bool) -> None:
    lang = cb.data.split(":")[1]
    async with Session() as s:
        u = await s.get(User, user.id)
        u.lang = lang
        await s.commit()
    user.lang = lang
    await cb.answer(t("lang_set", lang))
    try:
        await cb.message.delete()
    except Exception:  # noqa: BLE001
        pass
    await show_welcome(cb.message, user, is_admin)


@router.callback_query(F.data == "sub:check")
async def sub_ok(cb: CallbackQuery, user: User, is_admin: bool) -> None:
    await cb.answer("✅")
    await show_welcome(cb.message, user, is_admin)


@router.message(btn("btn_lang"))
@router.message(Command("lang"))
async def choose_lang(message: Message) -> None:
    await message.answer(t("choose_lang"), reply_markup=lang_kb())


@router.callback_query(F.data == "cancel")
async def cancel_cb(cb: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    await cb.answer(t("cancelled", lang))
    try:
        await cb.message.delete()
    except Exception:  # noqa: BLE001
        pass


@router.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext, lang: str, is_admin: bool) -> None:
    await state.clear()
    await message.answer(t("cancelled", lang), reply_markup=main_menu(lang, is_admin))


@router.message(btn("btn_faq"))
async def faq(message: Message, lang: str) -> None:
    await message.answer(settings.get(f"faq_{lang}") or settings.get("faq_ru"), disable_web_page_preview=True)


async def _ref_count(user_id: int) -> int:
    async with Session() as s:
        return await s.scalar(select(func.count(User.id)).where(User.referrer_id == user_id)) or 0


@router.message(btn("btn_profile"))
async def profile(message: Message, user: User, lang: str) -> None:
    async with Session() as s:
        row = (await s.execute(select(func.count(Order.id), func.coalesce(func.sum(Order.amount_rub), 0)).where(
            Order.user_id == user.id, Order.status.in_(("delivered", "waiting"))))).one()
        u = await s.get(User, user.id)
    await message.answer(t("profile", lang, id=user.id, orders=row[0], spent=money(row[1]),
                           disc=money(u.ref_discount or 0), refs=await _ref_count(user.id)))


@router.message(btn("btn_ref"))
async def referrals(message: Message, user: User, lang: str, bot: Bot) -> None:
    if not settings.get_bool("ref_enabled"):
        await message.answer(t("ref_disabled", lang))
        return
    me = await bot.me()
    levels = settings.ref_levels()
    word = "ур." if lang == "ru" else "lvl"
    lv = ", ".join(f"{i} {word} — {money(p)}%" for i, p in enumerate(levels, 1)) or "—"
    async with Session() as s:
        u = await s.get(User, user.id)
    await message.answer(t("ref_info", lang, levels=lv, max=money(settings.get_float("max_discount", 50)),
                           link=f"https://t.me/{me.username}?start=ref_{user.id}",
                           refs=await _ref_count(user.id), disc=money(u.ref_discount or 0)))


@router.message(btn("btn_purchases"))
async def purchases(message: Message, user: User, lang: str) -> None:
    async with Session() as s:
        rows = (await s.execute(select(Order, Product).join(Product, Product.id == Order.product_id, isouter=True)
                                .where(Order.user_id == user.id, Order.status.in_(("delivered", "waiting")))
                                .order_by(Order.id.desc()).limit(30))).all()
    if not rows:
        await message.answer(t("purchases_empty", lang))
        return
    kb = [[(f"#{o.id} · {p.name(lang) if p else '—'}", f"my:{o.id}")] for o, p in rows]
    await message.answer(t("purchases_title", lang), reply_markup=ikb(kb))


@router.callback_query(F.data.startswith("my:"))
async def purchase_detail(cb: CallbackQuery, user: User, lang: str) -> None:
    from app.db import Key
    oid = int(cb.data.split(":")[1])
    async with Session() as s:
        o = await s.get(Order, oid)
        if not o or o.user_id != user.id:
            await cb.answer()
            return
        p = await s.get(Product, o.product_id)
        k = await s.get(Key, o.key_id) if o.key_id else None
    text = t("order_info", lang, order=o.id, name=p.name(lang) if p else "—", date=o.created_at.strftime("%d.%m.%Y"))
    if k:
        text += "\n\n" + t("your_key", lang, key=html.escape(k.value), dur=shop.duration_text(k.duration_days, lang))
    elif o.status == "waiting":
        text += "\n\n" + t("waiting_key", lang)
    rows = []
    if p and shop.file_for(p)[0]:
        rows.append([bt("btn_get_file", lang, f"getfile:{o.id}")])
    if settings.get_bool("reviews_enabled"):
        rows.append([bt("btn_leave_review", lang, f"rev:new:{o.id}")])
    await cb.message.answer(text, reply_markup=ikb(rows) if rows else None)
    await cb.answer()


@router.callback_query(F.data.startswith("getfile:"))
async def get_file(cb: CallbackQuery, user: User, lang: str, bot: Bot) -> None:
    oid = int(cb.data.split(":")[1])
    async with Session() as s:
        o = await s.get(Order, oid)
        p = await s.get(Product, o.product_id) if o and o.user_id == user.id and o.status == "delivered" else None
    if not p or not await shop.send_file(bot, user.id, p):
        await cb.answer(t("no_file", lang), show_alert=True)
        return
    await cb.answer()


# ---------- Поддержка ----------
@router.message(btn("btn_support"))
async def support(message: Message, state: FSMContext, lang: str) -> None:
    contact = settings.get("support_contact").strip()
    await state.set_state(Support.text)
    text = t("support_contact", lang, c=html.escape(contact)) if contact else t("support_prompt", lang)
    await message.answer(text, reply_markup=cancel_kb(lang))


@router.message(Support.text)
async def support_msg(message: Message, state: FSMContext, user: User, lang: str, bot: Bot) -> None:
    await state.clear()
    head = (f"💬 Обращение от <code>{user.id}</code> @{html.escape(user.username or '-')} "
            f"({html.escape(user.first_name or '')})")
    kb = ikb([[("↩️ Ответить", f"adm:reply:{user.id}")]])
    for aid in admin_ids():
        try:
            await bot.send_message(aid, head)
            await message.copy_to(aid, reply_markup=kb)
        except Exception:  # noqa: BLE001
            pass
    await message.answer(t("support_sent", lang))
