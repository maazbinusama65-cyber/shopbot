"""FastAPI app: public /chat + /health (graded API), public catalogue, token-protected /admin."""
import hmac
import json
import logging
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from . import timeline as tl
from .config import settings
from .db import init_schema, insert_returning_id, one, rows, tx
from .graph import run_turn
from .seed import seed

log = logging.getLogger("shopbot")
ID_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,64}$")

app = FastAPI(title="ShopBot Agent API")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup() -> None:
    init_schema()
    seed()


# ------------------------------------------------------------------ graded API
class ChatIn(BaseModel):
    user_id: str
    thread_id: str
    message: str = Field(min_length=1)


_hits: dict[str, deque] = defaultdict(deque)


def _rate_limit(user_id: str) -> None:
    q, now = _hits[user_id], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.rate_limit_per_min:
        raise HTTPException(429, "Too many messages, please slow down.")
    q.append(now)


def _log(user_id, thread_id, role, content, tools=None, tin=0, tout=0, ms=0):
    with tx() as c:
        insert_returning_id(
            c, "INSERT INTO chat_log(user_id,thread_id,role,content,tool_calls_json,tokens_in,tokens_out,"
               "latency_ms,created_at) VALUES(:u,:t,:r,:c,:tc,:ti,:to,:ms,:ca)",
            u=user_id, t=thread_id, r=role, c=content, tc=json.dumps(tools or []), ti=tin, to=tout,
            ms=ms, ca=datetime.now(timezone.utc).isoformat(timespec="seconds"))


@app.post("/chat")
def chat(body: ChatIn) -> dict:
    if not ID_RE.match(body.user_id) or not ID_RE.match(body.thread_id):
        raise HTTPException(422, "user_id/thread_id must be 1-64 chars of [A-Za-z0-9_.:@-]")
    message = body.message.strip()[: settings.max_message_chars]
    _rate_limit(body.user_id)
    t0 = time.time()
    try:
        res = run_turn(body.user_id, body.thread_id, message)
    except Exception:
        log.exception("chat turn failed")
        res = {"reply": "Sorry, I hit a problem on my side. Please try again in a moment.",
               "tool_calls": [], "tokens": {"in": 0, "out": 0}}
    ms = int((time.time() - t0) * 1000)
    _log(body.user_id, body.thread_id, "user", message)
    _log(body.user_id, body.thread_id, "assistant", res["reply"], res["tool_calls"],
         res["tokens"]["in"], res["tokens"]["out"], ms)
    return res


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


# ------------------------------------------------------------------ public catalogue
@app.get("/products")
def products() -> list[dict]:
    with tx() as c:
        ps = rows(c, "SELECT id,name,category,description,stock FROM products WHERE active=1 ORDER BY id")
    out = []
    for p in ps:
        priced = tl.current_price(p["id"])
        out.append({**p, "price": priced[0] if priced else None})
    return out


# ------------------------------------------------------------------ admin
def admin(x_admin_token: str = Header(default="")) -> None:
    if not settings.admin_token:
        raise HTTPException(503, "ADMIN_TOKEN not configured")
    if not hmac.compare_digest(x_admin_token.encode(), settings.admin_token.encode()):
        raise HTTPException(401, "bad admin token")


class ProductIn(BaseModel):
    name: str
    category: str = "general"
    description: str = ""
    stock: int = Field(ge=0, default=0)
    price: float = Field(gt=0)


class ProductPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    stock: int | None = Field(default=None, ge=0)
    price: float | None = Field(default=None, gt=0)
    active: bool | None = None
    effective_from: str | None = None  # YYYY-MM-DD, lets the owner schedule a price change


class FactIn(BaseModel):
    subject: str
    relation: str
    object: str
    valid_from: str | None = None
    valid_to: str | None = None


@app.get("/admin/products", dependencies=[Depends(admin)])
def admin_products() -> list[dict]:
    with tx() as c:
        ps = rows(c, "SELECT * FROM products ORDER BY id")
    for p in ps:
        priced = tl.current_price(p["id"])
        p["price"] = priced[0] if priced else None
    return ps


@app.post("/admin/products", dependencies=[Depends(admin)])
def admin_create_product(p: ProductIn) -> dict:
    with tx() as c:
        pid = insert_returning_id(
            c, "INSERT INTO products(name,category,description,stock,active,created_at) "
               "VALUES(:n,:c,:d,:s,1,:t)", n=p.name, c=p.category, d=p.description, s=p.stock, t=tl.today())
    tl.add_fact(tl.SHOP, f"product:{pid}", "price", str(p.price), source="admin")
    return {"id": pid}


@app.patch("/admin/products/{pid}", dependencies=[Depends(admin)])
def admin_patch_product(pid: int, p: ProductPatch) -> dict:
    with tx() as c:
        if not one(c, "SELECT id FROM products WHERE id=:i", i=pid):
            raise HTTPException(404, "no such product")
        for col, val in (("name", p.name), ("description", p.description), ("stock", p.stock),
                         ("active", None if p.active is None else int(p.active))):
            if val is not None:
                c.execute(text(f"UPDATE products SET {col}=:v WHERE id=:i"), {"v": val, "i": pid})
    if p.price is not None:  # a price edit is a timeline event, not an overwrite
        tl.add_fact(tl.SHOP, f"product:{pid}", "price", str(p.price),
                    valid_from=p.effective_from, source="admin")
    return {"ok": True}


@app.get("/admin/timeline", dependencies=[Depends(admin)])
def admin_timeline(subject: str = "") -> list[dict]:
    with tx() as c:
        if subject:
            return rows(c, "SELECT * FROM edges WHERE owner='shop' AND subject=:s ORDER BY relation, valid_from", s=subject)
        return rows(c, "SELECT * FROM edges WHERE owner='shop' ORDER BY subject, relation, valid_from")


@app.post("/admin/facts", dependencies=[Depends(admin)])
def admin_add_fact(f: FactIn) -> dict:
    return {"id": tl.add_fact(tl.SHOP, f.subject, f.relation, f.object, f.valid_from, f.valid_to, "admin")}


@app.get("/admin/orders", dependencies=[Depends(admin)])
def admin_orders() -> list[dict]:
    with tx() as c:
        return rows(c, "SELECT * FROM orders ORDER BY id DESC LIMIT 100")


@app.get("/admin/conversations", dependencies=[Depends(admin)])
def admin_conversations() -> list[dict]:
    with tx() as c:
        return rows(c, "SELECT user_id, thread_id, COUNT(*) AS messages, MAX(created_at) AS last_at, "
                       "SUM(tokens_in) AS tokens_in, SUM(tokens_out) AS tokens_out "
                       "FROM chat_log GROUP BY user_id, thread_id ORDER BY last_at DESC LIMIT 100")


@app.get("/admin/conversations/{user_id}/{thread_id}", dependencies=[Depends(admin)])
def admin_conversation(user_id: str, thread_id: str) -> list[dict]:
    with tx() as c:
        return rows(c, "SELECT role,content,tool_calls_json,latency_ms,created_at FROM chat_log "
                       "WHERE user_id=:u AND thread_id=:t ORDER BY id", u=user_id, t=thread_id)


@app.get("/admin/stats", dependencies=[Depends(admin)])
def admin_stats() -> dict:
    with tx() as c:
        s = one(c, "SELECT COUNT(*) AS turns, COALESCE(SUM(tokens_in),0) AS tin, COALESCE(SUM(tokens_out),0) AS tout, "
                   "COALESCE(AVG(latency_ms),0) AS avg_ms, COUNT(DISTINCT user_id) AS users "
                   "FROM chat_log WHERE role='assistant'")
        o = one(c, "SELECT COUNT(*) AS orders, COALESCE(SUM(total),0) AS revenue FROM orders")
    cost = s["tin"] / 1e6 * settings.price_in_per_m + s["tout"] / 1e6 * settings.price_out_per_m
    return {**s, **o, "est_cost_usd": round(cost, 4), "model": settings.model}
