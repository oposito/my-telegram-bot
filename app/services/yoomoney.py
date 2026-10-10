"""ЮMoney: форма оплаты (карта/кошелёк) + проверка HTTP-уведомлений."""
import hashlib
from urllib.parse import urlencode

from app import settings


def enabled() -> bool:
    return settings.get_bool("pay_yoomoney") and bool(settings.get("yoomoney_wallet").strip())


def pay_url(order_id: int, amount: float, title: str, return_url: str | None) -> str:
    q = {
        "receiver": settings.get("yoomoney_wallet").strip(),
        "quickpay-form": "button",
        "paymentType": "AC",
        "sum": f"{amount:.2f}",
        "label": f"order:{order_id}",
        "targets": title[:150],
    }
    if return_url:
        q["successURL"] = return_url
    return "https://yoomoney.ru/quickpay/confirm?" + urlencode(q)


def check_notification(data: dict) -> bool:
    secret = settings.get("yoomoney_secret").strip()
    if not secret:
        return False
    parts = [data.get(k, "") for k in ("notification_type", "operation_id", "amount", "currency",
                                       "datetime", "sender", "codepro")]
    parts += [secret, data.get("label", "")]
    digest = hashlib.sha1("&".join(parts).encode()).hexdigest()
    return digest == data.get("sha1_hash", "")
