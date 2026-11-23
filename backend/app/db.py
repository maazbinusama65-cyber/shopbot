"""Database access. Plain SQL via SQLAlchemy so SQLite (dev) and Postgres (prod) both work."""
from contextlib import contextmanager

from sqlalchemy import create_engine, text

from .config import settings


def normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DB_URL = normalize_url(settings.database_url)
IS_PG = DB_URL.startswith("postgresql")

_kwargs = {"pool_pre_ping": True}
if IS_PG:
    # Supabase / Neon poolers run in transaction mode: no server-side prepared statements.
    _kwargs["connect_args"] = {"prepare_threshold": None}
else:
    _kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DB_URL, **_kwargs)

_PK = "SERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"

SCHEMA = [
    f"""CREATE TABLE IF NOT EXISTS products (
        id {_PK}, name TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'general',
        description TEXT NOT NULL DEFAULT '', stock INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)""",
    # M3 timeline memory: a dated graph. owner is 'shop' (global facts) or a user_id.
    f"""CREATE TABLE IF NOT EXISTS edges (
        id {_PK}, owner TEXT NOT NULL, subject TEXT NOT NULL, relation TEXT NOT NULL,
        object TEXT NOT NULL, valid_from TEXT NOT NULL, valid_to TEXT,
        source TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_edges_owner_subject ON edges(owner, subject, relation)",
    f"""CREATE TABLE IF NOT EXISTS orders (
        id {_PK}, user_id TEXT NOT NULL, items_json TEXT NOT NULL, total REAL NOT NULL,
        status TEXT NOT NULL, created_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)",
    f"""CREATE TABLE IF NOT EXISTS pending_actions (
        id {_PK}, user_id TEXT NOT NULL, thread_id TEXT NOT NULL, kind TEXT NOT NULL,
        payload_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)""",
    f"""CREATE TABLE IF NOT EXISTS chat_log (
        id {_PK}, user_id TEXT NOT NULL, thread_id TEXT NOT NULL, role TEXT NOT NULL,
        content TEXT NOT NULL, tool_calls_json TEXT NOT NULL DEFAULT '[]',
        tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,
        latency_ms INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_chat_user_thread ON chat_log(user_id, thread_id)",
]


def init_schema() -> None:
    with engine.begin() as conn:
        for stmt in SCHEMA:
            conn.execute(text(stmt))


@contextmanager
def tx():
    """Transactional connection; commits on success, rolls back on error."""
    with engine.begin() as conn:
        yield conn


def rows(conn, sql: str, **params) -> list[dict]:
    return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def one(conn, sql: str, **params) -> dict | None:
    r = conn.execute(text(sql), params).first()
    return dict(r._mapping) if r else None


def insert_returning_id(conn, sql: str, **params) -> int:
    """`sql` must be an INSERT without RETURNING; works on SQLite >= 3.35 and Postgres."""
    return conn.execute(text(sql + " RETURNING id"), params).scalar_one()
