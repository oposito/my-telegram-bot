from __future__ import annotations

import datetime as dt
import ssl as _ssl
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import (BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app import config


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    lang: Mapped[str | None] = mapped_column(String(4))
    referrer_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    ref_discount: Mapped[float] = mapped_column(Float, default=0.0)
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name_ru: Mapped[str] = mapped_column(String(128))
    name_en: Mapped[str] = mapped_column(String(128), default="")
    desc_ru: Mapped[str] = mapped_column(Text, default="")
    desc_en: Mapped[str] = mapped_column(Text, default="")
    price_rub: Mapped[float] = mapped_column(Float, default=0)
    price_stars: Mapped[int | None] = mapped_column(Integer)   # ручная цена в Stars
    price_usdt: Mapped[float | None] = mapped_column(Float)    # ручная цена в USDT
    use_keys: Mapped[bool] = mapped_column(Boolean, default=True)
    deliver_file: Mapped[bool] = mapped_column(Boolean, default=True)
    file_id: Mapped[str | None] = mapped_column(String(256))   # свой файл товара (иначе главный)
    file_name: Mapped[str | None] = mapped_column(String(256))
    icon: Mapped[str | None] = mapped_column(String(128))       # кастом-эмодзи "id|символ"
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    def name(self, lang: str) -> str:
        return (self.name_en if lang == "en" and self.name_en else self.name_ru) or "—"

    def desc(self, lang: str) -> str:
        return (self.desc_en if lang == "en" and self.desc_en else self.desc_ru) or ""


class Key(Base):
    __tablename__ = "keys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    value: Mapped[str] = mapped_column(Text)
    duration_days: Mapped[int | None] = mapped_column(Integer)  # None = бессрочно
    sold: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    order_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    method: Mapped[str] = mapped_column(String(16))  # stars / crypto / yoomoney / sbp / free / gift
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # pending -> paid -> delivered | waiting (нет ключей) | cancelled | rejected | refunded
    amount_rub: Mapped[float] = mapped_column(Float, default=0)
    pay_amount: Mapped[float] = mapped_column(Float, default=0)
    pay_currency: Mapped[str] = mapped_column(String(16), default="RUB")
    discount: Mapped[float] = mapped_column(Float, default=0)
    ref_used: Mapped[float] = mapped_column(Float, default=0)
    promo_code: Mapped[str | None] = mapped_column(String(64))
    external_id: Mapped[str | None] = mapped_column(String(128), index=True)
    pay_url: Mapped[str | None] = mapped_column(Text)
    charge_id: Mapped[str | None] = mapped_column(String(256))
    receipt_file_id: Mapped[str | None] = mapped_column(String(256))
    key_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime)


class Promo(Base):
    __tablename__ = "promos"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    percent: Mapped[float] = mapped_column(Float)
    max_uses: Mapped[int] = mapped_column(Integer, default=0)  # 0 = без лимита
    used: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PromoUse(Base):
    __tablename__ = "promo_uses"
    __table_args__ = (UniqueConstraint("code", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(BigInteger)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    order_id: Mapped[int] = mapped_column(Integer, unique=True)
    product_id: Mapped[int] = mapped_column(Integer)
    rating: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


def _prepare_url(url: str) -> tuple[str, dict]:
    connect_args: dict = {}
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    if url.startswith("postgresql+asyncpg://"):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        mode = query.pop("sslmode", None) or query.pop("ssl", None)
        if mode and mode not in ("disable", "allow", "prefer"):
            ctx = _ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
            connect_args["ssl"] = ctx
        query.pop("channel_binding", None)
        url = urlunsplit(parts._replace(query=urlencode(query)))
    return url, connect_args


_url, _args = _prepare_url(config.DATABASE_URL)
engine = create_async_engine(_url, connect_args=_args, pool_pre_ping=True)
Session: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)


def _add_missing_columns(conn) -> None:
    """Простая авто-миграция: добавляет новые колонки в уже существующие таблицы."""
    from sqlalchemy import inspect, text
    insp = inspect(conn)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in existing:
                ddl = col.type.compile(dialect=conn.dialect)
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}'))


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
