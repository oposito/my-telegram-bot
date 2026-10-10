TEXTS: dict[str, dict[str, str]] = {
    "choose_lang": {"ru": "🌐 Выберите язык / Choose language", "en": "🌐 Выберите язык / Choose language"},
    "btn_catalog": {"ru": "🛒 Каталог", "en": "🛒 Catalog"},
    "btn_profile": {"ru": "👤 Профиль", "en": "👤 Profile"},
    "btn_purchases": {"ru": "📦 Мои покупки", "en": "📦 My purchases"},
    "btn_reviews": {"ru": "⭐ Отзывы", "en": "⭐ Reviews"},
    "btn_ref": {"ru": "🤝 Рефералы", "en": "🤝 Referrals"},
    "btn_support": {"ru": "💬 Поддержка", "en": "💬 Support"},
    "btn_faq": {"ru": "❓ FAQ", "en": "❓ FAQ"},
    "btn_lang": {"ru": "🌐 Язык", "en": "🌐 Language"},
    "btn_admin": {"ru": "🛠 Админ-панель", "en": "🛠 Admin panel"},
    "btn_back": {"ru": "⬅️ Назад", "en": "⬅️ Back"},
    "btn_cancel": {"ru": "✖️ Отмена", "en": "✖️ Cancel"},
    "cancelled": {"ru": "Отменено.", "en": "Cancelled."},
    "banned": {"ru": "⛔ Вы заблокированы.", "en": "⛔ You are banned."},
    "need_sub": {"ru": "📢 Чтобы пользоваться ботом, подпишитесь на канал и нажмите «Проверить».",
                 "en": "📢 Please subscribe to the channel and press «Check» to use the bot."},
    "btn_subscribe": {"ru": "📢 Подписаться", "en": "📢 Subscribe"},
    "btn_check_sub": {"ru": "✅ Проверить", "en": "✅ Check"},
    "not_subscribed": {"ru": "Вы ещё не подписались.", "en": "You are not subscribed yet."},
    "catalog_empty": {"ru": "Каталог пока пуст.", "en": "The catalog is empty for now."},
    "catalog_title": {"ru": "🛒 <b>Каталог</b>\nВыберите товар:", "en": "🛒 <b>Catalog</b>\nChoose a product:"},
    "product_card": {"ru": "<b>{name}</b>\n\n{desc}\n\n💰 Цена: <b>{price}</b>\n📦 В наличии: {stock}",
                     "en": "<b>{name}</b>\n\n{desc}\n\n💰 Price: <b>{price}</b>\n📦 In stock: {stock}"},
    "your_discount": {"ru": "🎁 Ваша скидка: <b>{d}%</b> → <b>{price}</b>", "en": "🎁 Your discount: <b>{d}%</b> → <b>{price}</b>"},
    "stock_unlimited": {"ru": "много", "en": "plenty"},
    "btn_buy": {"ru": "💳 Купить", "en": "💳 Buy"},
    "btn_promo": {"ru": "🎟 Ввести промокод", "en": "🎟 Enter promo code"},
    "out_of_stock": {"ru": "😔 Товар закончился.", "en": "😔 Out of stock."},
    "choose_method": {"ru": "К оплате: <b>{price}</b> (скидка {d}%)\nВыберите способ оплаты:",
                      "en": "To pay: <b>{price}</b> (discount {d}%)\nChoose a payment method:"},
    "m_stars": {"ru": "⭐ Telegram Stars ({v} ⭐)", "en": "⭐ Telegram Stars ({v} ⭐)"},
    "m_crypto": {"ru": "💎 Криптовалюта (xRocket)", "en": "💎 Crypto (xRocket)"},
    "m_yoomoney": {"ru": "💳 Карта / ЮMoney ({v} ₽)", "en": "💳 Card / YooMoney ({v} ₽)"},
    "m_sbp": {"ru": "🏦 СБП ({v} ₽)", "en": "🏦 SBP ({v} ₽)"},
    "no_methods": {"ru": "Способы оплаты временно недоступны.", "en": "Payment methods are temporarily unavailable."},
    "choose_coin": {"ru": "Выберите монету:", "en": "Choose a coin:"},
    "enter_promo": {"ru": "Отправьте промокод:", "en": "Send the promo code:"},
    "promo_ok": {"ru": "✅ Промокод применён: −{p}%", "en": "✅ Promo applied: −{p}%"},
    "promo_bad": {"ru": "❌ Промокод недействителен.", "en": "❌ Invalid promo code."},
    "pay_crypto": {"ru": "💎 Счёт на <b>{amount} {cur}</b> создан.\nОплатите по кнопке, затем нажмите «Проверить оплату». Выдача также произойдёт автоматически.",
                   "en": "💎 Invoice for <b>{amount} {cur}</b> created.\nPay via the button, then press «Check payment». Delivery is automatic too."},
    "pay_yoomoney": {"ru": "💳 К оплате <b>{amount} ₽</b>.\nОплатите по кнопке — товар придёт автоматически после оплаты.",
                     "en": "💳 Amount: <b>{amount} ₽</b>.\nPay via the button — the product is delivered automatically."},
    "btn_pay": {"ru": "💸 Оплатить", "en": "💸 Pay"},
    "btn_check": {"ru": "🔄 Проверить оплату", "en": "🔄 Check payment"},
    "not_paid": {"ru": "Оплата ещё не поступила.", "en": "Payment not received yet."},
    "pay_error": {"ru": "⚠️ Не удалось создать счёт, попробуйте другой способ.", "en": "⚠️ Failed to create invoice, try another method."},
    "sbp_info": {"ru": "🏦 К оплате <b>{amount} ₽</b>\n\n{details}\n\nЗаказ №{order}", "en": "🏦 Amount: <b>{amount} ₽</b>\n\n{details}\n\nOrder #{order}"},
    "btn_i_paid": {"ru": "✅ Я оплатил", "en": "✅ I paid"},
    "send_receipt": {"ru": "📎 Пришлите скриншот или чек оплаты одним сообщением.", "en": "📎 Send a screenshot or receipt in one message."},
    "receipt_sent": {"ru": "⏳ Чек отправлен на проверку. Товар придёт после подтверждения.", "en": "⏳ Receipt sent for review. You will get the product after confirmation."},
    "sbp_rejected": {"ru": "❌ Оплата по заказу №{order} не подтверждена. Напишите в поддержку.", "en": "❌ Payment for order #{order} was not confirmed. Contact support."},
    "delivered": {"ru": "✅ <b>Спасибо за покупку!</b>\nЗаказ №{order}: {name}", "en": "✅ <b>Thank you for your purchase!</b>\nOrder #{order}: {name}"},
    "your_key": {"ru": "🔑 Ваш ключ:\n<code>{key}</code>\n⏳ Срок: {dur}", "en": "🔑 Your key:\n<code>{key}</code>\n⏳ Duration: {dur}"},
    "forever": {"ru": "бессрочно", "en": "lifetime"},
    "days": {"ru": "{n} дн.", "en": "{n} days"},
    "waiting_key": {"ru": "⏳ Оплата получена, но ключи временно закончились. Мы выдадим ключ автоматически, как только он появится.",
                    "en": "⏳ Payment received, but keys are temporarily out of stock. You will get a key automatically as soon as it is added."},
    "btn_leave_review": {"ru": "⭐ Оставить отзыв", "en": "⭐ Leave a review"},
    "file_updated": {"ru": "🆕 Вышло обновление файла! Актуальная версия:", "en": "🆕 The file was updated! Latest version:"},
    "profile": {"ru": "👤 <b>Профиль</b>\n\nID: <code>{id}</code>\nПокупок: {orders}\nПотрачено: {spent} ₽\n🎁 Накопленная скидка: {disc}%\n👥 Приглашено: {refs}",
                "en": "👤 <b>Profile</b>\n\nID: <code>{id}</code>\nPurchases: {orders}\nSpent: {spent} ₽\n🎁 Accumulated discount: {disc}%\n👥 Invited: {refs}"},
    "purchases_empty": {"ru": "У вас пока нет покупок.", "en": "You have no purchases yet."},
    "purchases_title": {"ru": "📦 <b>Ваши покупки</b>", "en": "📦 <b>Your purchases</b>"},
    "order_info": {"ru": "🧾 Заказ №{order}\n{name}\nДата: {date}", "en": "🧾 Order #{order}\n{name}\nDate: {date}"},
    "btn_get_file": {"ru": "📥 Скачать актуальный файл", "en": "📥 Download latest file"},
    "no_file": {"ru": "Файл пока не загружен.", "en": "No file uploaded yet."},
    "ref_info": {"ru": "🤝 <b>Реферальная программа</b>\n\nПриглашайте друзей по ссылке — когда они покупают, вы получаете скидку на свои покупки.\n\nУровни: {levels}\nМаксимальная скидка: {max}%\n\nВаша ссылка:\n<code>{link}</code>\n\n👥 Приглашено: {refs}\n🎁 Ваша скидка сейчас: {disc}%",
                 "en": "🤝 <b>Referral program</b>\n\nInvite friends with your link — when they buy, you get a discount on your purchases.\n\nLevels: {levels}\nMax discount: {max}%\n\nYour link:\n<code>{link}</code>\n\n👥 Invited: {refs}\n🎁 Your discount now: {disc}%"},
    "ref_disabled": {"ru": "Реферальная программа сейчас выключена.", "en": "The referral program is disabled."},
    "ref_bonus": {"ru": "🎉 Ваш реферал ({lvl}-й уровень) совершил покупку! Скидка +{p}%, теперь у вас {disc}%.",
                  "en": "🎉 Your referral (level {lvl}) made a purchase! Discount +{p}%, now you have {disc}%."},
    "reviews_title": {"ru": "⭐ <b>Отзывы</b>  (средняя оценка {avg} из 5, всего {n})", "en": "⭐ <b>Reviews</b>  (average {avg} of 5, total {n})"},
    "reviews_empty": {"ru": "Отзывов пока нет.", "en": "No reviews yet."},
    "btn_write_review": {"ru": "✍️ Написать отзыв", "en": "✍️ Write a review"},
    "review_need_order": {"ru": "Отзыв могут оставить только покупатели. Все ваши покупки уже с отзывами или покупок нет.",
                          "en": "Only buyers can leave reviews. You have no purchases without a review."},
    "review_choose_order": {"ru": "О какой покупке отзыв?", "en": "Which purchase is the review for?"},
    "review_rate": {"ru": "Оцените покупку:", "en": "Rate your purchase:"},
    "review_text": {"ru": "Напишите текст отзыва (или нажмите «Пропустить»):", "en": "Write your review (or press «Skip»):"},
    "btn_skip": {"ru": "Пропустить", "en": "Skip"},
    "review_sent": {"ru": "🙏 Спасибо! Отзыв отправлен на модерацию.", "en": "🙏 Thanks! Your review was sent for moderation."},
    "review_exists": {"ru": "Вы уже оставили отзыв на эту покупку.", "en": "You already reviewed this purchase."},
    "review_approved": {"ru": "✅ Ваш отзыв опубликован! Спасибо.", "en": "✅ Your review was published! Thanks."},
    "review_bonus": {"ru": "🎁 За отзыв начислена скидка +{p}%.", "en": "🎁 You got +{p}% discount for the review."},
    "review_rejected": {"ru": "Ваш отзыв не прошёл модерацию.", "en": "Your review did not pass moderation."},
    "support_prompt": {"ru": "💬 Напишите сообщение для поддержки (можно с фото):", "en": "💬 Write your message to support (photo allowed):"},
    "support_contact": {"ru": "💬 Поддержка: {c}\n\nИли напишите сообщение здесь:", "en": "💬 Support: {c}\n\nOr write your message here:"},
    "support_sent": {"ru": "✅ Сообщение отправлено. Ответ придёт сюда.", "en": "✅ Message sent. The reply will come here."},
    "support_reply": {"ru": "💬 <b>Ответ поддержки:</b>", "en": "💬 <b>Support reply:</b>"},
    "lang_set": {"ru": "✅ Язык: русский", "en": "✅ Language: English"},
    "main_menu": {"ru": "Главное меню 👇", "en": "Main menu 👇"},
}


import re
import string

from aiogram import F

from app import settings

ICON_KEYS = [k for k in TEXTS if k.startswith(("btn_", "m_"))]
_EMOJI_RE = re.compile(r"^[^\w\s<{]+\s*")


def override(_k: str, lang: str) -> str | None:
    v = settings.get(f"txt_{_k}_{lang}")
    return v or None


def raw(_k: str, lang: str) -> str:
    item = TEXTS.get(_k, {})
    return override(_k, lang) or item.get(lang) or item.get("ru", _k)


def t(_k: str, lang: str | None = "ru", **kw) -> str:
    lang = lang if lang in ("ru", "en") else "ru"
    if _k not in TEXTS:
        return _k
    text = raw(_k, lang)
    if not kw:
        return text
    try:
        return text.format(**kw)
    except (KeyError, IndexError, ValueError):
        item = TEXTS[_k]
        return (item.get(lang) or item["ru"]).format(**kw)


def placeholders(_k: str) -> list[str]:
    return sorted({f for _, f, _, _ in string.Formatter().parse(TEXTS[_k]["ru"]) if f})


def strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text, count=1).strip() or text


def icon(_k: str) -> str | None:
    """ID кастом-эмодзи, назначенного кнопке (или None)."""
    v = settings.get(f"ic_{_k}")
    return v.split("|")[0] if v else None


def button_text(_k: str, lang: str | None, **kw) -> str:
    text = t(_k, lang, **kw)
    return strip_emoji(text) if icon(_k) else text


def all_variants(_k: str) -> set[str]:
    out = set()
    for lang in ("ru", "en"):
        v = raw(_k, lang)
        out.update({v, strip_emoji(v)})
    return out


def btn(_k: str):
    """Фильтр для кнопок главного меню (учитывает изменённые в админке тексты)."""
    return F.text.func(lambda v: v in all_variants(_k))
