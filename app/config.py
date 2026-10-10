import os


def _ids(raw: str) -> set[int]:
    out = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return out


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
# Главный администратор (можно указать несколько через запятую)
ADMIN_IDS = _ids(os.getenv("ADMIN_IDS", "1607904992"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///shop.db").strip()
XROCKET_API_KEY = os.getenv("XROCKET_API_KEY", "").strip()
XROCKET_API_URL = os.getenv("XROCKET_API_URL", "https://pay.xrocket.tg").rstrip("/")
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")  # например https://tgatfd.infrlo.com
PORT = int(os.getenv("PORT", "8080"))
