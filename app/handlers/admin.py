import asyncio
import datetime as dt
import html
import io
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, MagicData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy import delete, distinct, func, or_, select, update

from app import config, settings
from app.db import Key, Order, Product, Promo, Review, Session, User, now
from app.i18n import ICON_KEYS, TEXTS, all_variants, btn, button_text, icon, placeholders, raw, t
from app.keyboards import ikb
from app.services import shop
from app.utils import chat_ref, coin_amount, extract_emoji, money, send_sticker, tg_emoji

log = logging.getLogger(__name__)
router = Router(name="admin")
router.message.filter(MagicData(F.is_admin))
router.callback_query.filter(MagicData(F.is_admin))


class Adm(StatesGroup):
    input = State()


CANCEL = ikb([[("✖️ Отмена", "adm:cancel")]])
BACK = [("⬅️ В админку", "adm:menu")]


async def show(target, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except Exception:  # noqa: BLE001
            await target.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb, disable_web_page_preview=True)


async def ask(target, state: FSMContext, kind: str, text: str, **data) -> None:
    await state.set_state(Adm.input)
    await state.update_data(kind=kind, **data)
    msg = target.message if isinstance(target, CallbackQuery) else target
    await msg.answer(text, reply_markup=CANCEL)
    if isinstance(target, CallbackQuery):
        await target.answer()


# ======================= Меню =======================
async def menu_kb() -> InlineKeyboardMarkup:
    async with Session() as s:
        pend_rev = await s.scalar(select(func.count(Review.id)).where(Review.status == "pending")) or 0
        pend_ord = await s.scalar(select(func.count(Order.id)).where(
            or_(Order.status == "waiting", (Order.method == "sbp") & (Order.status == "pending")
                & Order.receipt_file_id.is_not(None)))) or 0
    return ikb([
        [("📊 Статистика", "adm:stats"), ("📦 Товары и ключи", "adm:products")],
        [("📁 Главный файл", "adm:mainfile"), ("📣 Рассылка", "adm:bc")],
        [("👥 Пользователи", "adm:users"), ("🎟 Промокоды", "adm:promos")],
        [(f"⭐ Отзывы ({pend_rev})", "adm:reviews"), (f"🧾 Заказы ({pend_ord})", "adm:orders")],
        [("🎨 Оформление", "adm:design"), ("⚙️ Настройки", "adm:settings")],
    ])


@router.message(Command("admin"))
@router.message(btn("btn_admin"))
async def admin_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=await menu_kb())


@router.callback_query(F.data == "adm:menu")
async def admin_menu_cb(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await show(cb, "🛠 <b>Админ-панель</b>", await menu_kb())


@router.callback_query(F.data == "adm:cancel")
async def adm_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await cb.answer("Отменено")
    try:
        await cb.message.delete()
    except Exception:  # noqa: BLE001
        pass


# ======================= Статистика =======================
@router.callback_query(F.data == "adm:stats")
async def stats(cb: CallbackQuery) -> None:
    n = now()
    day, week, month = n - dt.timedelta(days=1), n - dt.timedelta(days=7), n - dt.timedelta(days=30)
    ok = Order.status.in_(("delivered", "waiting"))
    async with Session() as s:
        users = await s.scalar(select(func.count(User.id)))
        u_day = await s.scalar(select(func.count(User.id)).where(User.created_at >= day))
        u_week = await s.scalar(select(func.count(User.id)).where(User.created_at >= week))
        blocked = await s.scalar(select(func.count(User.id)).where(User.blocked_bot.is_(True)))
        buyers = await s.scalar(select(func.count(distinct(Order.user_id))).where(ok, Order.method != "gift"))

        async def rev(since=None):
            q = select(func.count(Order.id), func.coalesce(func.sum(Order.amount_rub), 0)).where(ok, Order.method != "gift")
            if since:
                q = q.where(Order.paid_at >= since)
            return (await s.execute(q)).one()
        r_all, r_day, r_week, r_month = await rev(), await rev(day), await rev(week), await rev(month)
        by_method = (await s.execute(select(Order.method, func.count(Order.id), func.coalesce(func.sum(Order.amount_rub), 0))
                                     .where(ok).group_by(Order.method))).all()
        prods = (await s.execute(select(Product).order_by(Product.sort, Product.id))).scalars().all()
    lines = [
        "📊 <b>Статистика</b>\n",
        f"👥 Пользователей: <b>{users}</b> (+{u_day} за сутки, +{u_week} за неделю)",
        f"🚫 Заблокировали бота: {blocked}",
        f"🛍 Покупателей: <b>{buyers}</b>\n",
        f"💰 Продажи (в ₽ по базовой цене):",
        f"• Сутки: {r_day[0]} шт. / {money(r_day[1])} ₽",
        f"• Неделя: {r_week[0]} шт. / {money(r_week[1])} ₽",
        f"• Месяц: {r_month[0]} шт. / {money(r_month[1])} ₽",
        f"• Всего: {r_all[0]} шт. / {money(r_all[1])} ₽\n",
        "💳 По способам: " + (", ".join(f"{m}: {c} ({money(sm)} ₽)" for m, c, sm in by_method) or "—"),
        "\n📦 Остатки ключей:",
    ]
    for p in prods:
        st = await shop.stock(p)
        lines.append(f"• {html.escape(p.name_ru)}: {'∞' if st is None else st}{'' if p.active else ' (скрыт)'}")
    await show(cb, "\n".join(lines), ikb([BACK]))


# ======================= Товары =======================
async def products_kb() -> InlineKeyboardMarkup:
    async with Session() as s:
        items = (await s.execute(select(Product).order_by(Product.sort, Product.id))).scalars().all()
    rows = [[(f"{'🟢' if p.active else '⚪️'} {p.name_ru} — {money(p.price_rub)} ₽", f"adm:p:{p.id}")] for p in items]
    rows.append([("➕ Добавить товар", "adm:padd")])
    rows.append(BACK)
    return ikb(rows)


@router.callback_query(F.data == "adm:products")
async def products(cb: CallbackQuery) -> None:
    await show(cb, "📦 <b>Товары</b>\n🟢 — виден в каталоге, ⚪️ — скрыт", await products_kb())


@router.callback_query(F.data == "adm:padd")
async def product_add(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(cb, state, "padd", "Отправьте название и цену в ₽ через «|».\nНапример: <code>Лицензия на 30 дней | 299</code>")


PFIELDS = {
    "name_ru": ("Название (RU)", "str"), "name_en": ("Название (EN)", "str"),
    "desc_ru": ("Описание (RU)", "text"), "desc_en": ("Описание (EN)", "text"),
    "price_rub": ("Цена, ₽", "float"), "price_stars": ("Ручная цена в ⭐ (пусто — авто)", "int?"),
    "price_usdt": ("Ручная цена в USDT (пусто — авто)", "float?"), "sort": ("Порядок сортировки", "int"),
    "icon": ("Кастом-эмодзи товара (пришлите эмодзи)", "emoji"),
}


async def product_card(target, pid: int) -> None:
    async with Session() as s:
        p = await s.get(Product, pid)
        if not p:
            await show(target, "Товар не найден", ikb([[("⬅️ Товары", "adm:products")]]))
            return
        sold = await s.scalar(select(func.count(Key.id)).where(Key.product_id == pid, Key.sold.is_(True)))
    st = await shop.stock(p)
    stars = shop.price_stars(p, 0)
    try:
        usdt = await shop.price_usdt(p, 0)
    except Exception:  # noqa: BLE001
        usdt = 0
    fid, fname = shop.file_for(p)
    text = (f"📦 {tg_emoji(p.icon)}<b>{html.escape(p.name_ru)}</b> (ID {p.id})\n"
            f"EN: {html.escape(p.name_en or '—')}\n\n"
            f"💰 Цена: <b>{money(p.price_rub)} ₽</b>\n"
            f"⭐ Stars: {stars}{' (ручная)' if p.price_stars else ' (авто)'}\n"
            f"💎 USDT: {usdt:.2f}{' (ручная)' if p.price_usdt else ' (авто)'}\n\n"
            f"Статус: {'🟢 в продаже' if p.active else '⚪️ скрыт'}\n"
            f"🔑 Выдавать ключи: {'да' if p.use_keys else 'нет'} — в наличии {'∞' if st is None else st}, продано {sold}\n"
            f"📁 Выдавать файл: {'да' if p.deliver_file else 'нет'} — "
            f"{('свой: ' + html.escape(p.file_name or 'файл')) if p.file_id else ('главный файл' if fid else 'файл не загружен')}\n\n"
            f"<b>RU описание:</b>\n{p.desc_ru or '—'}\n\n<b>EN описание:</b>\n{p.desc_en or '—'}")
    rows = [
        [("✏️ Название RU", f"adm:pe:{pid}:name_ru"), ("✏️ Название EN", f"adm:pe:{pid}:name_en")],
        [("📝 Описание RU", f"adm:pe:{pid}:desc_ru"), ("📝 Описание EN", f"adm:pe:{pid}:desc_en")],
        [("💰 Цена ₽", f"adm:pe:{pid}:price_rub"), ("⭐ Цена Stars", f"adm:pe:{pid}:price_stars"),
         ("💎 Цена USDT", f"adm:pe:{pid}:price_usdt")],
        [("➕ Добавить ключи", f"adm:pk:{pid}"), ("📄 Выгрузить ключи", f"adm:pkl:{pid}")],
        [("🗑 Удалить непроданные ключи", f"adm:pkc:{pid}")],
        [("📁 Свой файл товара", f"adm:pf:{pid}"), ("↩️ Использовать главный", f"adm:pfd:{pid}")],
        [(f"{'🙈 Скрыть' if p.active else '👁 Показать'}", f"adm:pt:{pid}:active"),
         (f"🔑 Ключи: {'вкл' if p.use_keys else 'выкл'}", f"adm:pt:{pid}:use_keys"),
         (f"📁 Файл: {'вкл' if p.deliver_file else 'выкл'}", f"adm:pt:{pid}:deliver_file")],
        [("✨ Кастом-эмодзи товара", f"adm:pe:{pid}:icon"), ("🔢 Сортировка", f"adm:pe:{pid}:sort")],
        [("❌ Удалить товар", f"adm:pdel:{pid}")],
        [("⬅️ Товары", "adm:products")],
    ]
    await show(target, text[:4000], ikb(rows))


@router.callback_query(F.data.startswith("adm:p:"))
async def product_open(cb: CallbackQuery) -> None:
    await product_card(cb, int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("adm:pt:"))
async def product_toggle(cb: CallbackQuery) -> None:
    _, _, pid, field = cb.data.split(":")
    async with Session() as s:
        p = await s.get(Product, int(pid))
        setattr(p, field, not getattr(p, field))
        await s.commit()
    await product_card(cb, int(pid))


@router.callback_query(F.data.startswith("adm:pe:"))
async def product_edit(cb: CallbackQuery, state: FSMContext) -> None:
    _, _, pid, field = cb.data.split(":")
    title, typ = PFIELDS[field]
    hint = "\nОтправьте «-», чтобы очистить (вернуть авто)." if typ.endswith("?") else ""
    if typ == "text":
        hint = "\nМожно использовать форматирование Telegram. «-» — очистить."
    await ask(cb, state, "pfield", f"Введите новое значение: <b>{title}</b>{hint}", pid=int(pid), field=field)


@router.callback_query(F.data.startswith("adm:pk:"))
async def keys_add(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(cb, state, "keys", "Отправьте ключи — по одному в строке — текстом или .txt файлом.\n\n"
                                 "Срок действия (в днях) указывается через «|»:\n"
                                 "<code>AAAA-BBBB-CCCC|30</code> — на 30 дней\n"
                                 "<code>DDDD-EEEE-FFFF</code> — бессрочно",
              pid=int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("adm:pkl:"))
async def keys_list(cb: CallbackQuery) -> None:
    pid = int(cb.data.split(":")[2])
    async with Session() as s:
        keys = (await s.execute(select(Key).where(Key.product_id == pid).order_by(Key.sold, Key.id))).scalars().all()
    if not keys:
        await cb.answer("Ключей нет", show_alert=True)
        return
    lines = [f"{k.value}|{k.duration_days or 0}\t{'ПРОДАН (заказ ' + str(k.order_id) + ')' if k.sold else 'свободен'}"
             for k in keys]
    await cb.message.answer_document(BufferedInputFile("\n".join(lines).encode(), filename=f"keys_{pid}.txt"))
    await cb.answer()


@router.callback_query(F.data.startswith("adm:pkc:"))
async def keys_clear(cb: CallbackQuery) -> None:
    pid = cb.data.split(":")[2]
    await show(cb, "Удалить все <b>непроданные</b> ключи этого товара?",
               ikb([[("✅ Да, удалить", f"adm:pkc2:{pid}"), ("⬅️ Нет", f"adm:p:{pid}")]]))


@router.callback_query(F.data.startswith("adm:pkc2:"))
async def keys_clear2(cb: CallbackQuery) -> None:
    pid = int(cb.data.split(":")[2])
    async with Session() as s:
        res = await s.execute(delete(Key).where(Key.product_id == pid, Key.sold.is_(False)))
        await s.commit()
    await cb.answer(f"Удалено: {res.rowcount}", show_alert=True)
    await product_card(cb, pid)


@router.callback_query(F.data.startswith("adm:pf:"))
async def pfile(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(cb, state, "pfile", "Отправьте файл (документом) для этого товара.", pid=int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("adm:pfd:"))
async def pfile_del(cb: CallbackQuery) -> None:
    pid = int(cb.data.split(":")[2])
    async with Session() as s:
        p = await s.get(Product, pid)
        p.file_id, p.file_name = None, None
        await s.commit()
    await cb.answer("Теперь выдаётся главный файл", show_alert=True)
    await product_card(cb, pid)


@router.callback_query(F.data.startswith("adm:pdel:"))
async def product_del(cb: CallbackQuery) -> None:
    pid = cb.data.split(":")[2]
    await show(cb, "Удалить товар вместе с непроданными ключами? История заказов сохранится.\n"
                   "Совет: можно просто скрыть товар.",
               ikb([[("✅ Удалить", f"adm:pdel2:{pid}"), ("⬅️ Нет", f"adm:p:{pid}")]]))


@router.callback_query(F.data.startswith("adm:pdel2:"))
async def product_del2(cb: CallbackQuery) -> None:
    pid = int(cb.data.split(":")[2])
    async with Session() as s:
        await s.execute(delete(Key).where(Key.product_id == pid, Key.sold.is_(False)))
        await s.execute(delete(Product).where(Product.id == pid))
        await s.commit()
    await show(cb, "Товар удалён.", await products_kb())


# ======================= Главный файл =======================
@router.callback_query(F.data == "adm:mainfile")
async def mainfile(cb: CallbackQuery) -> None:
    fid = settings.get("main_file_id")
    text = ("📁 <b>Главный файл</b>\nВыдаётся всем покупателям товаров, у которых нет своего файла.\n\n"
            + (f"Текущий: <b>{html.escape(settings.get('main_file_name') or 'файл')}</b>\n"
               f"Версия: {settings.get('main_file_version') or 1}\nОбновлён: {settings.get('main_file_updated') or '—'}"
               if fid else "Файл ещё не загружен."))
    rows = [[("⬆️ Загрузить новую версию", "adm:mfup")]]
    if fid:
        rows.append([("📥 Получить текущий", "adm:mfget"), ("📣 Разослать покупателям", "adm:mfsend")])
    rows.append(BACK)
    await show(cb, text, ikb(rows))


@router.callback_query(F.data == "adm:mfup")
async def mainfile_up(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(cb, state, "mainfile", "Отправьте новый файл документом (можно с подписью — она уйдёт в рассылку об обновлении).")


@router.callback_query(F.data == "adm:mfget")
async def mainfile_get(cb: CallbackQuery) -> None:
    await cb.message.answer_document(settings.get("main_file_id"))
    await cb.answer()


async def buyers_for_file(pid: int | None) -> list[int]:
    async with Session() as s:
        q = select(distinct(Order.user_id)).join(Product, Product.id == Order.product_id).where(
            Order.status == "delivered", Product.deliver_file.is_(True))
        q = q.where(Product.id == pid) if pid else q.where(Product.file_id.is_(None))
        return list((await s.execute(q)).scalars().all())


async def send_file_update(bot: Bot, admin_id: int, pid: int | None) -> None:
    users = await buyers_for_file(pid)
    note = settings.get("main_file_note") if not pid else ""
    async with Session() as s:
        p = await s.get(Product, pid) if pid else None
        langs = dict((await s.execute(select(User.id, User.lang).where(User.id.in_(users)))).all()) if users else {}
    fid = p.file_id if p else settings.get("main_file_id")
    ok = fail = 0
    for uid in users:
        try:
            cap = t("file_updated", langs.get(uid)) + (f"\n\n{note}" if note else "")
            await bot.send_document(uid, fid, caption=cap[:1024])
            ok += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:  # noqa: BLE001
            fail += 1
        await asyncio.sleep(0.05)
    await bot.send_message(admin_id, f"📣 Обновление файла разослано: ✅ {ok}, ❌ {fail}")


@router.callback_query(F.data == "adm:mfsend")
async def mainfile_send(cb: CallbackQuery, bot: Bot) -> None:
    asyncio.create_task(send_file_update(bot, cb.from_user.id, None))
    await cb.answer("Рассылка запущена", show_alert=True)


@router.callback_query(F.data.startswith("adm:pfsend:"))
async def pfile_send(cb: CallbackQuery, bot: Bot) -> None:
    asyncio.create_task(send_file_update(bot, cb.from_user.id, int(cb.data.split(":")[2])))
    await cb.answer("Рассылка запущена", show_alert=True)


# ======================= Рассылка =======================
@router.callback_query(F.data == "adm:bc")
async def bc(cb: CallbackQuery) -> None:
    await show(cb, "📣 <b>Рассылка</b>\nКому отправить?", ikb([
        [("👥 Всем", "adm:bca:all")],
        [("🇷🇺 Русским", "adm:bca:ru"), ("🇬🇧 Английским", "adm:bca:en")],
        [("🛍 Покупателям", "adm:bca:buyers"), ("🙅 Без покупок", "adm:bca:nobuy")],
        BACK]))


@router.callback_query(F.data.startswith("adm:bca:"))
async def bc_aud(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(cb, state, "bc", "Отправьте сообщение для рассылки (текст, фото, видео, файл, опрос — что угодно).",
              aud=cb.data.split(":")[2])


async def audience(aud: str) -> list[int]:
    async with Session() as s:
        q = select(User.id).where(User.banned.is_(False), User.blocked_bot.is_(False))
        buyers = select(Order.user_id).where(Order.status.in_(("delivered", "waiting")))
        if aud == "ru":
            q = q.where(or_(User.lang == "ru", User.lang.is_(None)))
        elif aud == "en":
            q = q.where(User.lang == "en")
        elif aud == "buyers":
            q = q.where(User.id.in_(buyers))
        elif aud == "nobuy":
            q = q.where(User.id.not_in(buyers))
        return list((await s.execute(q)).scalars().all())


def bc_markup(btn: str | None) -> InlineKeyboardMarkup | None:
    if not btn:
        return None
    rows = []
    for line in btn.splitlines():
        if "|" in line:
            txt, url = line.split("|", 1)
            rows.append([(txt.strip(), url.strip())])
    return ikb(rows) if rows else None


async def bc_preview(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.set_state(None)
    kb = bc_markup(data.get("bc_btn"))
    await bot.copy_message(message.chat.id, data["bc_chat"], data["bc_msg"], reply_markup=kb)
    n = len(await audience(data["aud"]))
    await message.answer(f"☝️ Так будет выглядеть рассылка. Получателей: <b>{n}</b>. Отправляем?",
                         reply_markup=ikb([[("🚀 Отправить", "adm:bcgo"), ("✖️ Отмена", "adm:menu")]]))


@router.callback_query(F.data == "adm:bcnobtn")
async def bc_nobtn(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.update_data(bc_btn=None)
    await cb.answer()
    await bc_preview(cb.message, state, bot)


@router.callback_query(F.data == "adm:bcgo")
async def bc_go(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    if not data.get("bc_msg"):
        await cb.answer("Нет сообщения", show_alert=True)
        return
    await state.update_data(bc_msg=None)
    await cb.message.edit_text("🚀 Рассылка запущена, по окончании пришлю отчёт.")
    asyncio.create_task(run_broadcast(bot, cb.from_user.id, data["bc_chat"], data["bc_msg"],
                                      data.get("bc_btn"), data["aud"]))
    await cb.answer()


async def run_broadcast(bot: Bot, admin_id: int, chat_id: int, msg_id: int, btn: str | None, aud: str) -> None:
    users = await audience(aud)
    kb = bc_markup(btn)
    ok = fail = 0
    blocked = []
    for uid in users:
        for _ in range(3):
            try:
                await bot.copy_message(uid, chat_id, msg_id, reply_markup=kb)
                ok += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except TelegramForbiddenError:
                blocked.append(uid)
                fail += 1
                break
            except Exception:  # noqa: BLE001
                fail += 1
                break
        await asyncio.sleep(0.04)
    if blocked:
        async with Session() as s:
            await s.execute(update(User).where(User.id.in_(blocked)).values(blocked_bot=True))
            await s.commit()
    await bot.send_message(admin_id, f"📣 Рассылка завершена\n✅ Доставлено: {ok}\n❌ Ошибок: {fail} (из них заблокировали бота: {len(blocked)})")


# ======================= Пользователи =======================
@router.callback_query(F.data == "adm:users")
async def users(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(cb, state, "usearch", "Отправьте ID или @username пользователя.")


async def user_card(target, uid: int) -> None:
    async with Session() as s:
        u = await s.get(User, uid)
        if not u:
            await show(target, "Пользователь не найден.", ikb([BACK]))
            return
        cnt, spent = (await s.execute(select(func.count(Order.id), func.coalesce(func.sum(Order.amount_rub), 0)).where(
            Order.user_id == uid, Order.status.in_(("delivered", "waiting"))))).one()
        refs = await s.scalar(select(func.count(User.id)).where(User.referrer_id == uid))
    text = (f"👤 <b>{html.escape(u.first_name or '')}</b> @{html.escape(u.username or '-')}\n"
            f"ID: <code>{u.id}</code>\nЯзык: {u.lang or '—'}\nРегистрация: {u.created_at:%d.%m.%Y %H:%M}\n"
            f"Пригласил: {u.referrer_id or '—'}\nПриглашено: {refs}\n"
            f"Покупок: {cnt} на {money(spent)} ₽\nСкидка: {money(u.ref_discount or 0)}%\n"
            f"Статус: {'⛔ заблокирован' if u.banned else '✅ активен'}{' · заблокировал бота' if u.blocked_bot else ''}")
    await show(target, text, ikb([
        [("✅ Разблокировать" if u.banned else "⛔ Заблокировать", f"adm:uban:{uid}")],
        [("🎁 Изменить скидку", f"adm:udisc:{uid}"), ("✉️ Написать", f"adm:reply:{uid}")],
        [("🎁 Выдать товар бесплатно", f"adm:ugive:{uid}")],
        [("🧾 Заказы", f"adm:uorders:{uid}")],
        BACK]))


@router.callback_query(F.data.startswith("adm:u:"))
async def user_open(cb: CallbackQuery) -> None:
    await user_card(cb, int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("adm:uban:"))
async def user_ban(cb: CallbackQuery) -> None:
    uid = int(cb.data.split(":")[2])
    if uid in config.ADMIN_IDS:
        await cb.answer("Нельзя заблокировать главного админа", show_alert=True)
        return
    async with Session() as s:
        u = await s.get(User, uid)
        u.banned = not u.banned
        await s.commit()
    await user_card(cb, uid)


@router.callback_query(F.data.startswith("adm:udisc:"))
async def user_disc(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(cb, state, "udisc", "Введите новую накопленную скидку пользователя в % (например 15, 0 — сбросить).",
              uid=int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("adm:reply:"))
async def user_reply(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(cb, state, "reply", "Напишите сообщение пользователю (можно с фото/файлом).", uid=int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("adm:ugive:"))
async def user_give(cb: CallbackQuery) -> None:
    uid = cb.data.split(":")[2]
    async with Session() as s:
        items = (await s.execute(select(Product).order_by(Product.sort, Product.id))).scalars().all()
    await show(cb, "Какой товар выдать?", ikb([[(p.name_ru, f"adm:ugp:{uid}:{p.id}")] for p in items]
                                              + [[("⬅️ Назад", f"adm:u:{uid}")]]))


@router.callback_query(F.data.startswith("adm:ugp:"))
async def user_give2(cb: CallbackQuery, bot: Bot) -> None:
    _, _, uid, pid = cb.data.split(":")
    async with Session() as s:
        u = await s.get(User, int(uid))
        p = await s.get(Product, int(pid))
        o = Order(user_id=u.id, product_id=p.id, method="gift", amount_rub=0, pay_amount=0, pay_currency="RUB")
        s.add(o)
        await s.commit()
        await s.refresh(o)
    await shop.fulfill(bot, o.id)
    await cb.answer(f"Выдано, заказ №{o.id}", show_alert=True)


@router.callback_query(F.data.startswith("adm:uorders:"))
async def user_orders(cb: CallbackQuery) -> None:
    uid = int(cb.data.split(":")[2])
    async with Session() as s:
        rows = (await s.execute(select(Order).where(Order.user_id == uid).order_by(Order.id.desc()).limit(30))).scalars().all()
    await show(cb, "🧾 Заказы пользователя:" if rows else "Заказов нет.",
               ikb([[(f"#{o.id} · {o.method} · {o.status} · {money(o.amount_rub)} ₽", f"adm:o:{o.id}")] for o in rows]
                   + [[("⬅️ Назад", f"adm:u:{uid}")]]))


# ======================= Заказы =======================
@router.callback_query(F.data == "adm:orders")
async def orders(cb: CallbackQuery) -> None:
    async with Session() as s:
        rows = (await s.execute(select(Order).where(or_(
            Order.status == "waiting",
            (Order.method == "sbp") & (Order.status == "pending") & Order.receipt_file_id.is_not(None)))
            .order_by(Order.id.desc()).limit(40))).scalars().all()
    kb = [[(f"#{o.id} · {'⏳ ждёт ключ' if o.status == 'waiting' else '🏦 СБП на проверке'} · {money(o.amount_rub)} ₽",
            f"adm:o:{o.id}")] for o in rows]
    kb += [[("🔎 Найти заказ по номеру", "adm:ofind")], BACK]
    await show(cb, "🧾 <b>Заказы, требующие внимания</b>" if rows else "🧾 Нет заказов, требующих внимания.", ikb(kb))


@router.callback_query(F.data == "adm:ofind")
async def order_find(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(cb, state, "ofind", "Введите номер заказа.")


async def order_card(target, oid: int, bot: Bot) -> None:
    async with Session() as s:
        o = await s.get(Order, oid)
        if not o:
            await show(target, "Заказ не найден.", ikb([BACK]))
            return
        p = await s.get(Product, o.product_id)
        k = await s.get(Key, o.key_id) if o.key_id else None
    text = (f"🧾 <b>Заказ №{o.id}</b>\nТовар: {html.escape(p.name_ru if p else '—')}\n"
            f"Покупатель: <code>{o.user_id}</code>\nСпособ: {o.method}\nСтатус: <b>{o.status}</b>\n"
            f"Сумма: {money(o.amount_rub)} ₽ (оплата: {coin_amount(o.pay_amount)} {o.pay_currency})\n"
            f"Скидка: {money(o.discount)}%{' · промо ' + o.promo_code if o.promo_code else ''}\n"
            f"Создан: {o.created_at:%d.%m.%Y %H:%M}" + (f"\nОплачен: {o.paid_at:%d.%m.%Y %H:%M}" if o.paid_at else "")
            + (f"\nКлюч: <code>{html.escape(k.value)}</code>" if k else ""))
    rows = []
    if o.method == "sbp" and o.status == "pending":
        rows.append([("✅ Подтвердить и выдать автоматически", f"adm:sbpok:{o.id}")])
        rows.append([("✍️ Выдать вручную", f"adm:sbpman:{o.id}"), ("❌ Отклонить", f"adm:sbpno:{o.id}")])
    elif o.status == "waiting":
        rows.append([("✍️ Выдать вручную", f"adm:sbpman:{o.id}")])
    if o.method == "stars" and o.charge_id and o.status in ("delivered", "waiting"):
        rows.append([("↩️ Вернуть Stars", f"adm:refund:{o.id}")])
    if o.status == "pending":
        rows.append([("✅ Отметить оплаченным и выдать", f"adm:oforce:{o.id}")])
    rows.append([("👤 Покупатель", f"adm:u:{o.user_id}")])
    rows.append(BACK)
    await show(target, text, ikb(rows))
    if o.receipt_file_id and isinstance(target, CallbackQuery):
        try:
            await bot.send_document(target.from_user.id, o.receipt_file_id, caption=f"Чек к заказу №{o.id}")
        except Exception:  # noqa: BLE001
            try:
                await bot.send_photo(target.from_user.id, o.receipt_file_id, caption=f"Чек к заказу №{o.id}")
            except Exception:  # noqa: BLE001
                pass


@router.callback_query(F.data.startswith("adm:o:"))
async def order_open(cb: CallbackQuery, bot: Bot) -> None:
    await order_card(cb, int(cb.data.split(":")[2]), bot)


@router.callback_query(F.data.startswith("adm:sbpok:") | F.data.startswith("adm:oforce:"))
async def sbp_ok(cb: CallbackQuery, bot: Bot) -> None:
    oid = int(cb.data.split(":")[2])
    if await shop.fulfill(bot, oid):
        await cb.answer(f"Заказ №{oid} выдан", show_alert=True)
    else:
        await cb.answer("Заказ уже обработан или ждёт ключи", show_alert=True)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("adm:sbpno:"))
async def sbp_no(cb: CallbackQuery, bot: Bot) -> None:
    oid = int(cb.data.split(":")[2])
    async with Session() as s:
        res = await s.execute(update(Order).where(Order.id == oid, Order.status == "pending").values(status="rejected"))
        await s.commit()
        o = await s.get(Order, oid)
        u = await s.get(User, o.user_id) if o else None
    if res.rowcount and u:
        try:
            await bot.send_message(u.id, t("sbp_rejected", u.lang, order=oid))
        except Exception:  # noqa: BLE001
            pass
    await cb.answer("Отклонено", show_alert=True)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("adm:refund:"))
async def refund(cb: CallbackQuery, bot: Bot) -> None:
    oid = int(cb.data.split(":")[2])
    async with Session() as s:
        o = await s.get(Order, oid)
    try:
        await bot.refund_star_payment(o.user_id, o.charge_id)
    except Exception as e:  # noqa: BLE001
        await cb.answer(f"Ошибка возврата: {e}"[:200], show_alert=True)
        return
    await shop.set_order(oid, status="refunded")
    await cb.answer("Stars возвращены", show_alert=True)


# ======================= Промокоды =======================
@router.callback_query(F.data == "adm:promos")
async def promos(cb: CallbackQuery) -> None:
    async with Session() as s:
        items = (await s.execute(select(Promo).order_by(Promo.code))).scalars().all()
    rows = []
    for p in items:
        lim = f"{p.used}/{p.max_uses}" if p.max_uses else f"{p.used}/∞"
        exp = f" до {p.expires_at:%d.%m}" if p.expires_at else ""
        rows.append([(f"{'🟢' if p.active else '⚪️'} {p.code} −{money(p.percent)}% ({lim}){exp}", f"adm:pr:{p.code}")])
    rows += [[("➕ Создать промокод", "adm:pradd")], BACK]
    await show(cb, "🎟 <b>Промокоды</b>\nНажмите на промокод, чтобы включить/выключить или удалить.", ikb(rows))


@router.callback_query(F.data == "adm:pradd")
async def promo_add(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(cb, state, "promo", "Отправьте: <code>КОД ПРОЦЕНТ [ЛИМИТ] [ДНЕЙ]</code>\n"
                                  "Например: <code>SALE20 20 100 7</code> — скидка 20%, 100 активаций, 7 дней.\n"
                                  "Лимит 0 — без ограничений.")


@router.callback_query(F.data.startswith("adm:pr:"))
async def promo_open(cb: CallbackQuery) -> None:
    code = cb.data.split(":", 2)[2]
    await show(cb, f"Промокод <b>{html.escape(code)}</b>", ikb([
        [("🔁 Вкл/выкл", f"adm:prt:{code}"), ("🗑 Удалить", f"adm:prd:{code}")], [("⬅️ Промокоды", "adm:promos")]]))


@router.callback_query(F.data.startswith("adm:prt:") | F.data.startswith("adm:prd:"))
async def promo_toggle(cb: CallbackQuery) -> None:
    action, code = cb.data.split(":")[1], cb.data.split(":", 2)[2]
    async with Session() as s:
        p = await s.get(Promo, code)
        if p:
            if action == "prd":
                await s.delete(p)
            else:
                p.active = not p.active
            await s.commit()
    await promos(cb)


# ======================= Отзывы =======================
@router.callback_query(F.data == "adm:reviews")
async def reviews_mod(cb: CallbackQuery) -> None:
    from app.handlers.reviews import stars
    async with Session() as s:
        rows = (await s.execute(select(Review).where(Review.status == "pending").order_by(Review.id).limit(10))).scalars().all()
    await show(cb, f"⭐ На модерации: {len(rows)}" + ("" if rows else "\nНовых отзывов нет.") +
               "\n\nУдалить опубликованный отзыв: <code>/delreview НОМЕР</code>", ikb([BACK]))
    for r in rows:
        await cb.message.answer(f"📝 Отзыв №{r.id} от <code>{r.user_id}</code>\n{stars(r.rating)}\n\n"
                                f"{html.escape(r.text) or '<i>без текста</i>'}",
                                reply_markup=ikb([[("✅ Опубликовать", f"adm:revok:{r.id}"),
                                                   ("❌ Отклонить", f"adm:revno:{r.id}")]]))


@router.callback_query(F.data.startswith("adm:revok:") | F.data.startswith("adm:revno:"))
async def review_decide(cb: CallbackQuery, bot: Bot) -> None:
    from app.handlers.reviews import stars
    approve = cb.data.startswith("adm:revok:")
    rid = int(cb.data.split(":")[2])
    async with Session() as s:
        res = await s.execute(update(Review).where(Review.id == rid, Review.status == "pending")
                              .values(status="approved" if approve else "rejected"))
        await s.commit()
        r = await s.get(Review, rid)
        u = await s.get(User, r.user_id) if r else None
        p = await s.get(Product, r.product_id) if r else None
    if not res.rowcount:
        await cb.answer("Уже обработан", show_alert=True)
        return
    lang = u.lang if u else "ru"
    if approve:
        ch = settings.get("reviews_channel").strip()
        if ch:
            body = (f"{stars(r.rating)}\n<b>{html.escape((u.first_name if u else None) or 'Покупатель')}</b>"
                    + (f" · {html.escape(p.name_ru)}" if p else "") + (f"\n\n{html.escape(r.text)}" if r.text else ""))
            try:
                await bot.send_message(chat_ref(ch), body)
            except Exception as e:  # noqa: BLE001
                await cb.message.answer(f"⚠️ Не удалось опубликовать в канал: {html.escape(str(e))}\n"
                                        "Проверьте, что бот — администратор канала.")
        try:
            await send_sticker(bot, r.user_id, "sticker_review")
            await bot.send_message(r.user_id, t("review_approved", lang))
            bonus = settings.get_float("review_bonus")
            if bonus > 0:
                await shop.add_discount(r.user_id, bonus)
                await bot.send_message(r.user_id, t("review_bonus", lang, p=money(bonus)))
        except Exception:  # noqa: BLE001
            pass
    else:
        try:
            await bot.send_message(r.user_id, t("review_rejected", lang))
        except Exception:  # noqa: BLE001
            pass
    await cb.answer("Опубликован" if approve else "Отклонён")
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass


@router.message(Command("delreview"))
async def del_review(message: Message) -> None:
    arg = (message.text or "").split()[1:]
    if not arg or not arg[0].isdigit():
        await message.answer("Использование: /delreview НОМЕР")
        return
    async with Session() as s:
        res = await s.execute(delete(Review).where(Review.id == int(arg[0])))
        await s.commit()
    await message.answer("Удалён." if res.rowcount else "Не найден.")


# ======================= Настройки =======================
def short(v: str, n: int = 22) -> str:
    v = (v or "—").replace("\n", " ")
    return v if len(v) <= n else v[:n - 1] + "…"


@router.callback_query(F.data == "adm:settings")
async def settings_menu(cb: CallbackQuery) -> None:
    await show(cb, "⚙️ <b>Настройки</b>", ikb([[(title, f"adm:sg:{g}")] for g, title in settings.GROUPS.items()] + [BACK]))


async def group_view(target, group: str) -> None:
    rows = []
    for o in settings.OPTIONS:
        if o.group != group:
            continue
        val = settings.get(o.key)
        if o.type == "bool":
            shown = "✅" if settings.get_bool(o.key) else "❌"
        elif o.type == "sticker":
            shown = "✅ задан" if val else "—"
        elif "token" in o.key or "secret" in o.key:
            shown = "•••" if val else "—"
        else:
            shown = short(val)
        rows.append([(f"{o.title}: {shown}", f"adm:s:{o.key}")])
    rows.append([("⬅️ Настройки", "adm:settings")])
    await show(target, f"⚙️ <b>{settings.GROUPS[group]}</b>\nНажмите на параметр, чтобы изменить.", ikb(rows))


@router.callback_query(F.data.startswith("adm:sg:"))
async def settings_group(cb: CallbackQuery) -> None:
    await group_view(cb, cb.data.split(":")[2])


@router.callback_query(F.data.startswith("adm:s:"))
async def setting_open(cb: CallbackQuery, state: FSMContext) -> None:
    key = cb.data.split(":", 2)[2]
    o = settings.BY_KEY[key]
    if key == "extra_admins" and cb.from_user.id not in config.ADMIN_IDS:
        await cb.answer("Только главный администратор", show_alert=True)
        return
    if o.type == "bool":
        await settings.put(key, "0" if settings.get_bool(key) else "1")
        await group_view(cb, o.group)
        return
    cur = settings.get(key)
    if "token" in key or "secret" in key:
        cur = "•••" if cur else "—"
    if o.type == "sticker":
        if cur:
            await cb.message.answer_sticker(cur)
        cur = "стикер выше ☝️" if cur else "—"
    await ask(cb, state, "setting", f"<b>{o.title}</b>\n{o.hint}\n\nТекущее значение:\n{cur or '—'}\n\n"
                                    "Отправьте новое значение. «-» — очистить/по умолчанию.", key=key)


# ======================= Оформление =======================
@router.callback_query(F.data == "adm:design")
async def design(cb: CallbackQuery) -> None:
    await show(cb, "🎨 <b>Оформление</b>\n\n"
                   "• <b>Кастом-эмодзи</b> (премиум) можно вставлять в любые тексты: приветствие, FAQ, описания, "
                   "реквизиты, рассылки и тексты бота — просто отправляйте их как обычно.\n"
                   "• На кнопки ставятся иконки из кастом-эмодзи.\n"
                   "• Стикеры (в т.ч. премиум и анимированные) — при старте, после покупки, отзыва и ответа поддержки.\n\n"
                   "⚠️ Кастом-эмодзи у ботов работают, только если у <b>владельца бота</b> (аккаунт, создавший бота в "
                   "@BotFather) есть Telegram Premium. Без него бот автоматически покажет обычные эмодзи.",
               ikb([[("✨ Иконки кнопок", "adm:icons:0")], [("🖼 Стикеры", "adm:sg:design")],
                    [("📝 Тексты бота", "adm:texts:0")], BACK]))


ICON_PAGE = 10


async def icons_view(target, page: int) -> None:
    keys = ICON_KEYS[page * ICON_PAGE:(page + 1) * ICON_PAGE]
    rows = [[(f"{'✅' if icon(k) else '▫️'} {raw(k, 'ru').format_map(_Blank())[:40]}", f"adm:ic:{k}:{page}")] for k in keys]
    nav = []
    if page > 0:
        nav.append(("◀️", f"adm:icons:{page - 1}"))
    if (page + 1) * ICON_PAGE < len(ICON_KEYS):
        nav.append(("▶️", f"adm:icons:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([("⬅️ Оформление", "adm:design")])
    await show(target, "✨ <b>Иконки кнопок</b>\n✅ — иконка задана. Нажмите на кнопку, чтобы задать или убрать иконку.", ikb(rows))


class _Blank(dict):
    def __missing__(self, key):
        return "…"


@router.callback_query(F.data.startswith("adm:icons:"))
async def icons(cb: CallbackQuery) -> None:
    await icons_view(cb, int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("adm:ic:"))
async def icon_edit(cb: CallbackQuery, state: FSMContext) -> None:
    _, _, key, page = cb.data.split(":")
    await ask(cb, state, "icon", f"Кнопка: <b>{html.escape(raw(key, 'ru'))}</b>\n\n"
                                 "Пришлите одно кастом-эмодзи (премиум) — оно станет иконкой кнопки. "
                                 "Обычный эмодзи в начале текста кнопки при этом скроется.\n«-» — убрать иконку.",
              key=key, page=int(page))


TEXT_PAGE = 12
TEXT_KEYS = list(TEXTS)


@router.callback_query(F.data.startswith("adm:texts:"))
async def texts(cb: CallbackQuery) -> None:
    page = int(cb.data.split(":")[2])
    keys = TEXT_KEYS[page * TEXT_PAGE:(page + 1) * TEXT_PAGE]
    rows = [[(f"{'✏️' if settings.get(f'txt_{k}_ru') or settings.get(f'txt_{k}_en') else '▫️'} "
              f"{short(raw(k, 'ru'), 38)}", f"adm:tx:{k}")] for k in keys]
    nav = []
    if page > 0:
        nav.append(("◀️", f"adm:texts:{page - 1}"))
    if (page + 1) * TEXT_PAGE < len(TEXT_KEYS):
        nav.append(("▶️", f"adm:texts:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([("⬅️ Оформление", "adm:design")])
    await show(cb, f"📝 <b>Тексты бота</b> (стр. {page + 1}/{(len(TEXT_KEYS) - 1) // TEXT_PAGE + 1})\n"
                   "✏️ — изменён. Можно использовать кастом-эмодзи и форматирование.", ikb(rows))


async def text_view(target, key: str) -> None:
    ph = placeholders(key)
    page = TEXT_KEYS.index(key) // TEXT_PAGE
    body = (f"📝 <b>Текст:</b> <code>{key}</code>\n"
            + (f"Переменные: {', '.join('{' + p + '}' for p in ph)}\n" if ph else "")
            + ("<i>Это кнопка: форматирование не сохранится, эмодзи на кнопку — в «Иконках кнопок».</i>\n"
               if key.startswith(("btn_", "m_")) else "")
            + f"\n🇷🇺 RU:\n{raw(key, 'ru')}\n\n🇬🇧 EN:\n{raw(key, 'en')}")
    await show(target, body[:4000], ikb([
        [("✏️ Изменить RU", f"adm:txe:{key}:ru"), ("✏️ Изменить EN", f"adm:txe:{key}:en")],
        [("↩️ Вернуть стандартный", f"adm:txr:{key}")],
        [("⬅️ К списку", f"adm:texts:{page}")]]))


@router.callback_query(F.data.startswith("adm:tx:"))
async def text_open(cb: CallbackQuery) -> None:
    await text_view(cb, cb.data.split(":", 2)[2])


@router.callback_query(F.data.startswith("adm:txe:"))
async def text_edit(cb: CallbackQuery, state: FSMContext) -> None:
    _, _, key, lang = cb.data.split(":")
    ph = placeholders(key)
    await ask(cb, state, "text", f"Отправьте новый текст ({lang.upper()}). "
                                 + (f"Обязательно оставьте переменные: {', '.join('{' + p + '}' for p in ph)}. "
                                    if ph else "")
                                 + "«-» — вернуть стандартный.", key=key, lang=lang)


@router.callback_query(F.data.startswith("adm:txr:"))
async def text_reset(cb: CallbackQuery) -> None:
    key = cb.data.split(":", 2)[2]
    await settings.put(f"txt_{key}_ru", "")
    await settings.put(f"txt_{key}_en", "")
    await text_view(cb, key)


# ======================= Ручная выдача =======================
@router.callback_query(F.data.startswith("adm:sbpman:"))
async def manual_delivery(cb: CallbackQuery, state: FSMContext) -> None:
    oid = int(cb.data.split(":")[2])
    await ask(cb, state, "manual", f"✍️ Ручная выдача заказа №{oid}.\n"
                                   "Отправьте то, что получит покупатель: ключ, текст, файл, фото — одним сообщением. "
                                   "Заказ будет отмечен выданным.", oid=oid)


# ======================= Ввод данных =======================
def _num(text: str, typ: str):
    text = text.strip().replace(",", ".").replace(" ", "")
    return int(float(text)) if typ.startswith("int") else float(text)


@router.message(Adm.input)
async def admin_input(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    kind = data.get("kind")
    text = message.text or message.caption or ""
    menu_words = set().union(*(all_variants(k) for k in ("btn_catalog", "btn_profile", "btn_purchases", "btn_reviews",
                                                          "btn_ref", "btn_support", "btn_faq", "btn_lang", "btn_admin")))
    if message.text in menu_words and kind not in ("bc",):
        await state.set_state(None)
        await message.answer("Ввод отменён. Нажмите кнопку ещё раз.")
        return
    html_text = message.html_text if (message.text or message.caption) else ""

    try:
        if kind == "padd":
            if "|" not in text:
                await message.answer("Формат: <code>Название | Цена</code>", reply_markup=CANCEL)
                return
            name, price = text.split("|", 1)
            async with Session() as s:
                p = Product(name_ru=name.strip()[:128], name_en=name.strip()[:128], price_rub=_num(price, "float"))
                s.add(p)
                await s.commit()
                await s.refresh(p)
            await state.set_state(None)
            await message.answer("✅ Товар создан. Добавьте описание, ключи и файл.")
            await product_card(message, p.id)

        elif kind == "pfield":
            field = data["field"]
            typ = PFIELDS[field][1]
            if typ == "emoji":
                value = None if text.strip() == "-" else extract_emoji(message)
                if text.strip() != "-" and not value:
                    await message.answer("Не нашёл кастом-эмодзи. Пришлите сообщение с премиум-эмодзи или его ID.",
                                         reply_markup=CANCEL)
                    return
                async with Session() as s:
                    p = await s.get(Product, data["pid"])
                    p.icon = value
                    await s.commit()
                await state.set_state(None)
                await product_card(message, data["pid"])
                return
            if text.strip() == "-":
                value = None if typ.endswith("?") else ""
            elif typ in ("int", "int?", "float", "float?"):
                value = _num(text, typ)
            elif typ == "text":
                value = html_text
            else:
                value = text.strip()[:128]
            if value is None and not typ.endswith("?"):
                value = ""
            async with Session() as s:
                p = await s.get(Product, data["pid"])
                setattr(p, field, value if value != "" or typ in ("str", "text") else 0)
                await s.commit()
            await state.set_state(None)
            await product_card(message, data["pid"])

        elif kind == "keys":
            raw = text
            if message.document:
                f = await bot.download(message.document)
                raw = f.read().decode("utf-8", errors="ignore")
            keys = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                days = None
                if "|" in line:
                    line, d = line.rsplit("|", 1)
                    d = d.strip()
                    days = int(d) if d.isdigit() and int(d) > 0 else None
                    line = line.strip()
                if line:
                    keys.append(Key(product_id=data["pid"], value=line, duration_days=days))
            if not keys:
                await message.answer("Ключи не найдены, попробуйте ещё раз.", reply_markup=CANCEL)
                return
            async with Session() as s:
                s.add_all(keys)
                await s.commit()
            await state.set_state(None)
            done = await shop.process_waiting(bot, data["pid"])
            await message.answer(f"✅ Добавлено ключей: {len(keys)}" + (f"\n📦 Выдано ожидающим заказам: {done}" if done else ""))
            await product_card(message, data["pid"])

        elif kind in ("pfile", "mainfile"):
            if not message.document:
                await message.answer("Нужно отправить файл именно документом.", reply_markup=CANCEL)
                return
            doc = message.document
            await state.set_state(None)
            if kind == "pfile":
                async with Session() as s:
                    p = await s.get(Product, data["pid"])
                    p.file_id, p.file_name = doc.file_id, doc.file_name
                    await s.commit()
                await message.answer(f"✅ Файл товара обновлён: {html.escape(doc.file_name or '')}",
                                     reply_markup=ikb([[("📣 Отправить покупателям этого товара", f"adm:pfsend:{data['pid']}")],
                                                       [("⬅️ К товару", f"adm:p:{data['pid']}")]]))
            else:
                ver = int(settings.get("main_file_version") or 0) + 1
                await settings.put("main_file_id", doc.file_id)
                await settings.put("main_file_name", doc.file_name or "file")
                await settings.put("main_file_version", str(ver))
                await settings.put("main_file_updated", now().strftime("%d.%m.%Y %H:%M UTC"))
                await settings.put("main_file_note", html_text)
                await message.answer(f"✅ Главный файл обновлён (версия {ver}).\nВсе новые покупатели получат его. "
                                     "Разослать обновление тем, кто уже купил?",
                                     reply_markup=ikb([[("📣 Разослать", "adm:mfsend"), ("Не нужно", "adm:menu")]]))

        elif kind == "bc":
            await state.update_data(bc_chat=message.chat.id, bc_msg=message.message_id, kind="bcbtn")
            await message.answer("Добавить кнопки-ссылки? Отправьте по одной в строке:\n"
                                 "<code>Текст кнопки | https://ссылка</code>",
                                 reply_markup=ikb([[("Без кнопок", "adm:bcnobtn")], [("✖️ Отмена", "adm:cancel")]]))

        elif kind == "bcbtn":
            await state.update_data(bc_btn=text)
            await bc_preview(message, state, bot)

        elif kind == "usearch":
            q = text.strip().lstrip("@")
            async with Session() as s:
                u = await s.get(User, int(q)) if q.isdigit() else await s.scalar(
                    select(User).where(func.lower(User.username) == q.lower()))
            await state.set_state(None)
            if not u:
                await message.answer("Не найден.", reply_markup=ikb([[("🔎 Ещё раз", "adm:users")], BACK]))
            else:
                await user_card(message, u.id)

        elif kind == "udisc":
            v = max(0.0, min(100.0, _num(text, "float")))
            async with Session() as s:
                u = await s.get(User, data["uid"])
                u.ref_discount = v
                await s.commit()
            await state.set_state(None)
            await user_card(message, data["uid"])

        elif kind == "reply":
            async with Session() as s:
                u = await s.get(User, data["uid"])
            await state.set_state(None)
            try:
                await send_sticker(bot, data["uid"], "sticker_support")
                await bot.send_message(data["uid"], t("support_reply", u.lang if u else "ru"))
                await message.copy_to(data["uid"])
                await message.answer("✅ Отправлено.")
            except Exception as e:  # noqa: BLE001
                await message.answer(f"❌ Не доставлено: {html.escape(str(e))}")

        elif kind == "ofind":
            await state.set_state(None)
            if text.strip().lstrip("#").isdigit():
                await order_card(message, int(text.strip().lstrip("#")), bot)
            else:
                await message.answer("Нужен номер заказа.")

        elif kind == "promo":
            parts = text.split()
            if len(parts) < 2:
                await message.answer("Формат: <code>КОД ПРОЦЕНТ [ЛИМИТ] [ДНЕЙ]</code>", reply_markup=CANCEL)
                return
            code, pct = parts[0].upper()[:64], _num(parts[1], "float")
            lim = int(parts[2]) if len(parts) > 2 else 0
            days = int(parts[3]) if len(parts) > 3 else 0
            async with Session() as s:
                existing = await s.get(Promo, code)
                if existing:
                    await s.delete(existing)
                    await s.flush()
                s.add(Promo(code=code, percent=max(0, min(100, pct)), max_uses=lim,
                            expires_at=now() + dt.timedelta(days=days) if days else None))
                await s.commit()
            await state.set_state(None)
            await message.answer(f"✅ Промокод <code>{html.escape(code)}</code> создан.",
                                 reply_markup=ikb([[("🎟 Промокоды", "adm:promos")]]))

        elif kind == "manual":
            await state.set_state(None)
            if await shop.deliver_manual(bot, data["oid"], message):
                await message.answer(f"✅ Заказ №{data['oid']} выдан вручную, покупатель получил ваше сообщение.")
            else:
                await message.answer("⚠️ Заказ уже обработан или сообщение не доставлено.")

        elif kind == "icon":
            key = data["key"]
            if text.strip() == "-":
                await settings.put(f"ic_{key}", "")
            else:
                value = extract_emoji(message)
                if not value:
                    await message.answer("Не нашёл кастом-эмодзи. Пришлите сообщение с премиум-эмодзи или его ID.",
                                         reply_markup=CANCEL)
                    return
                await settings.put(f"ic_{key}", value)
            await state.set_state(None)
            await message.answer("✅ Сохранено. Главное меню обновится после /start.")
            await icons_view(message, data.get("page", 0))

        elif kind == "text":
            key, lang = data["key"], data["lang"]
            if text.strip() == "-":
                value = ""
            else:
                value = text.strip() if key.startswith(("btn_", "m_")) else html_text
                try:
                    value.format(**{ph: "1" for ph in placeholders(key)})
                except (KeyError, IndexError, ValueError):
                    await message.answer("❌ В тексте неверные {переменные}. Используйте только: "
                                         + (", ".join("{" + p + "}" for p in placeholders(key)) or "нет"),
                                         reply_markup=CANCEL)
                    return
            await settings.put(f"txt_{key}_{lang}", value)
            await state.set_state(None)
            await message.answer("✅ Текст сохранён.")
            await text_view(message, key)

        elif kind == "setting":
            key = data["key"]
            o = settings.BY_KEY[key]
            if text.strip() == "-":
                value = o.default if key not in ("required_channel", "reviews_channel", "support_contact",
                                                 "xrocket_token", "yoomoney_secret", "yoomoney_wallet",
                                                 "crypto_rates", "extra_admins", "required_channel_link") else ""
            elif o.type == "sticker":
                if not message.sticker:
                    await message.answer("Пришлите именно стикер (или «-»).", reply_markup=CANCEL)
                    return
                value = message.sticker.file_id
            elif o.type in ("int", "float"):
                value = str(_num(text, o.type))
            elif o.type == "text":
                value = html_text
            else:
                value = text.strip()
            await settings.put(key, value)
            await state.set_state(None)
            await message.answer("✅ Сохранено.")
            await group_view(message, o.group)
        else:
            await state.set_state(None)
    except ValueError:
        await message.answer("❌ Неверное число, попробуйте ещё раз.", reply_markup=CANCEL)
