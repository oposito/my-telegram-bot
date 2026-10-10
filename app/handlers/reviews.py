import html

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from app import settings
from app.db import Order, Product, Review, Session, User
from app.i18n import all_variants, btn, t, button_text, icon
from app.keyboards import bt, ikb
from app.utils import admin_ids

router = Router(name="reviews")
PER_PAGE = 5


class Rev(StatesGroup):
    text = State()


def stars(n: int) -> str:
    return "⭐" * n + "☆" * (5 - n)


async def render_reviews(lang: str, page: int):
    async with Session() as s:
        total, avg = (await s.execute(select(func.count(Review.id), func.avg(Review.rating))
                                      .where(Review.status == "approved"))).one()
        rows = (await s.execute(select(Review, User, Product)
                                .join(User, User.id == Review.user_id, isouter=True)
                                .join(Product, Product.id == Review.product_id, isouter=True)
                                .where(Review.status == "approved").order_by(Review.id.desc())
                                .offset(page * PER_PAGE).limit(PER_PAGE))).all()
    head = t("reviews_title", lang, avg=f"{(avg or 0):.1f}", n=total)
    parts = [head]
    if not rows:
        parts.append(t("reviews_empty", lang))
    for r, u, p in rows:
        name = html.escape((u.first_name if u else None) or "User")
        line = f"\n{stars(r.rating)} — <b>{name}</b>"
        if p:
            line += f" · {html.escape(p.name(lang))}"
        if r.text:
            line += f"\n<i>{html.escape(r.text[:500])}</i>"
        parts.append(line)
    nav = []
    if page > 0:
        nav.append(("◀️", f"revs:{page - 1}"))
    if (page + 1) * PER_PAGE < total:
        nav.append(("▶️", f"revs:{page + 1}"))
    kb = [nav] if nav else []
    kb.append([bt("btn_write_review", lang, "rev:pick")])
    return "\n".join(parts), ikb(kb)


@router.message(btn("btn_reviews"))
async def reviews(message: Message, lang: str) -> None:
    text, kb = await render_reviews(lang, 0)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("revs:"))
async def reviews_page(cb: CallbackQuery, lang: str) -> None:
    text, kb = await render_reviews(lang, int(cb.data.split(":")[1]))
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data == "rev:pick")
async def pick(cb: CallbackQuery, lang: str, user: User) -> None:
    async with Session() as s:
        reviewed = select(Review.order_id)
        rows = (await s.execute(select(Order, Product).join(Product, Product.id == Order.product_id)
                                .where(Order.user_id == user.id, Order.status == "delivered",
                                       Order.id.not_in(reviewed)).order_by(Order.id.desc()).limit(20))).all()
    if not rows:
        await cb.answer(t("review_need_order", lang), show_alert=True)
        return
    await cb.message.answer(t("review_choose_order", lang),
                            reply_markup=ikb([[(f"#{o.id} · {p.name(lang)}", f"rev:new:{o.id}")] for o, p in rows]))
    await cb.answer()


@router.callback_query(F.data.startswith("rev:new:"))
async def new_review(cb: CallbackQuery, lang: str, user: User) -> None:
    if not settings.get_bool("reviews_enabled"):
        await cb.answer()
        return
    oid = int(cb.data.split(":")[2])
    async with Session() as s:
        o = await s.get(Order, oid)
        exists = await s.scalar(select(Review.id).where(Review.order_id == oid))
    if not o or o.user_id != user.id or o.status != "delivered":
        await cb.answer(t("review_need_order", lang), show_alert=True)
        return
    if exists:
        await cb.answer(t("review_exists", lang), show_alert=True)
        return
    await cb.message.answer(t("review_rate", lang),
                            reply_markup=ikb([[(str(i) + "⭐", f"rev:rate:{oid}:{i}") for i in range(1, 6)]]))
    await cb.answer()


@router.callback_query(F.data.startswith("rev:rate:"))
async def rate(cb: CallbackQuery, lang: str, state: FSMContext) -> None:
    _, _, oid, r = cb.data.split(":")
    await state.set_state(Rev.text)
    await state.update_data(rev_order=int(oid), rev_rating=int(r))
    await cb.message.edit_text(f"{stars(int(r))}\n\n" + t("review_text", lang),
                               reply_markup=ikb([[bt("btn_skip", lang, "rev:skip")]]))
    await cb.answer()


@router.callback_query(F.data == "rev:skip", Rev.text)
async def skip_text(cb: CallbackQuery, lang: str, state: FSMContext, user: User, bot: Bot) -> None:
    await _save(cb.message, state, user, lang, bot, "")
    await cb.answer()


@router.message(Rev.text, F.text)
async def review_text(message: Message, lang: str, state: FSMContext, user: User, bot: Bot) -> None:
    await _save(message, state, user, lang, bot, message.text[:1500])


async def _save(message: Message, state: FSMContext, user: User, lang: str, bot: Bot, text: str) -> None:
    data = await state.get_data()
    await state.set_state(None)
    oid, rating = data.get("rev_order"), data.get("rev_rating")
    async with Session() as s:
        o = await s.get(Order, oid or 0)
        if not o or o.user_id != user.id or await s.scalar(select(Review.id).where(Review.order_id == o.id)):
            await message.answer(t("review_exists", lang))
            return
        r = Review(user_id=user.id, order_id=o.id, product_id=o.product_id, rating=rating, text=text)
        s.add(r)
        await s.commit()
        p = await s.get(Product, o.product_id)
    await message.answer(t("review_sent", lang))
    body = (f"📝 Новый отзыв №{r.id} на модерацию\n{stars(rating)}\n"
            f"От: <code>{user.id}</code> @{html.escape(user.username or '-')}\n"
            f"Товар: {html.escape(p.name_ru if p else '-')}\n\n{html.escape(text) or '<i>без текста</i>'}")
    kb = ikb([[("✅ Опубликовать", f"adm:revok:{r.id}"), ("❌ Отклонить", f"adm:revno:{r.id}")]])
    for aid in admin_ids():
        try:
            await bot.send_message(aid, body, reply_markup=kb)
        except Exception:  # noqa: BLE001
            pass
