"""Orders and the two-step (propose -> confirm) flow for risky actions."""
import json
from datetime import datetime, timezone

from sqlalchemy import text

from . import timeline as tl
from .db import insert_returning_id, one, rows, tx


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def free_shipping_threshold() -> float:
    f = tl.facts_as_of(tl.SHOP, subject="policy:shipping", relation="free_over")
    return float(f[0]["object"]) if f else 0.0


def build_quote(items: list[dict]) -> dict:
    """Validate items against live stock/prices. Raises ValueError with a user-safe message."""
    lines, total = [], 0.0
    if not items:
        raise ValueError("The order has no items.")
    for it in items[:10]:
        pid, qty = int(it["product_id"]), int(it.get("qty", 1))
        if qty < 1 or qty > 20:
            raise ValueError("Quantity must be between 1 and 20 per item.")
        with tx() as c:
            p = one(c, "SELECT * FROM products WHERE id=:i AND active=1", i=pid)
        if not p:
            raise ValueError(f"Product #{pid} does not exist.")
        if p["stock"] < qty:
            raise ValueError(f"Only {p['stock']} of '{p['name']}' in stock (you asked for {qty}).")
        priced = tl.current_price(pid)
        if not priced:
            raise ValueError(f"'{p['name']}' has no price right now.")
        price, fact_id = priced
        lines.append({"product_id": pid, "name": p["name"], "qty": qty,
                      "unit_price": price, "price_fact": fact_id})
        total += price * qty
    return {"lines": lines, "subtotal": round(total, 2)}


def propose_order(user_id: str, thread_id: str, items: list[dict]) -> dict:
    quote = build_quote(items)
    with tx() as c:
        # only one open proposal per (user, thread): replace the old one
        c.execute(text("UPDATE pending_actions SET status='superseded' WHERE user_id=:u AND "
                       "thread_id=:t AND status='pending'"), {"u": user_id, "t": thread_id})
        insert_returning_id(
            c, "INSERT INTO pending_actions(user_id,thread_id,kind,payload_json,status,created_at) "
               "VALUES(:u,:t,'order',:p,'pending',:ca)",
            u=user_id, t=thread_id, p=json.dumps(quote), ca=_now())
    return quote


def get_pending(user_id: str, thread_id: str) -> dict | None:
    with tx() as c:
        r = one(c, "SELECT * FROM pending_actions WHERE user_id=:u AND thread_id=:t AND "
                   "status='pending' ORDER BY id DESC", u=user_id, t=thread_id)
    return r


def resolve_pending(pending_id: int, status: str) -> None:
    with tx() as c:
        c.execute(text("UPDATE pending_actions SET status=:s WHERE id=:i"),
                  {"s": status, "i": pending_id})


def execute_pending_order(pending: dict) -> dict:
    """Re-validate against current stock/prices, then place the order atomically."""
    quote_old = json.loads(pending["payload_json"])
    quote = build_quote([{"product_id": l["product_id"], "qty": l["qty"]} for l in quote_old["lines"]])
    with tx() as c:
        for l in quote["lines"]:
            res = c.execute(text("UPDATE products SET stock=stock-:q WHERE id=:i AND stock>=:q"),
                            {"q": l["qty"], "i": l["product_id"]})
            if res.rowcount != 1:
                raise ValueError(f"'{l['name']}' just went out of stock.")
        oid = insert_returning_id(
            c, "INSERT INTO orders(user_id,items_json,total,status,created_at) VALUES(:u,:i,:t,'placed',:ca)",
            u=pending["user_id"], i=json.dumps(quote["lines"]), t=quote["subtotal"], ca=_now())
        c.execute(text("UPDATE pending_actions SET status='done' WHERE id=:i"), {"i": pending["id"]})
    return {"order_id": oid, **quote, "price_changed": quote["subtotal"] != quote_old["subtotal"]}


def orders_for_user(user_id: str, limit: int = 10) -> list[dict]:
    with tx() as c:
        return rows(c, "SELECT * FROM orders WHERE user_id=:u ORDER BY id DESC LIMIT :n", u=user_id, n=limit)
