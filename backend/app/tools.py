"""Agent tools. user_id / thread_id come from the request config, never from model arguments,
so the model cannot be talked into reading another user's data."""
import json
from datetime import date

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from . import orders as od
from . import timeline as tl
from .db import rows, tx


def _ids(config: RunnableConfig) -> tuple[str, str]:
    c = config["configurable"]
    return c["user_id"], c["raw_thread_id"]


def _valid_date(s: str) -> str | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        return None


@tool
def search_products(query: str = "", category: str = "", max_price: float = 0,
                    config: RunnableConfig = None) -> str:
    """Search the catalogue. Returns id, name, current price (with the fact id to cite), stock.
    `query` matches name/description, `category` one of shoes/bags/accessories/outdoor/clothing,
    `max_price` 0 means no limit."""
    sql = "SELECT * FROM products WHERE active=1"
    params: dict = {}
    if category:
        sql += " AND LOWER(category)=:c"
        params["c"] = category.lower()
    terms = [t for t in query.lower().split() if len(t) > 2][:4]
    for i, t in enumerate(terms):
        sql += f" AND (LOWER(name) LIKE :t{i} OR LOWER(description) LIKE :t{i} OR LOWER(category) LIKE :t{i})"
        params[f"t{i}"] = f"%{t}%"
    with tx() as c:
        prods = rows(c, sql + " ORDER BY id LIMIT 8", **params)
    out = []
    for p in prods:
        priced = tl.current_price(p["id"])
        if not priced or (max_price and priced[0] > max_price):
            continue
        price, fid = priced
        stock = "out of stock" if p["stock"] == 0 else f"{p['stock']} in stock"
        out.append(f"#{p['id']} {p['name']} [{p['category']}] ${price:.2f} [F{fid}] {stock} - {p['description']}")
    return "<data>" + ("\n".join(out) or "No matching products.") + "</data>"


@tool
def get_price_history(product_id: int, as_of: str = "", config: RunnableConfig = None) -> str:
    """Timeline of a product's price (all past and current values with the dates they applied).
    Pass `as_of` (YYYY-MM-DD) to learn which price applied on that date."""
    hist = tl.history(tl.SHOP, f"product:{int(product_id)}", "price")
    if not hist:
        return "<data>No price history for that product id.</data>"
    d = _valid_date(as_of)
    lines = []
    for f in hist:
        mark = ""
        if d:
            mark = "  <-- APPLIED on " + d if tl.is_valid_on(f, d) else ""
        lines.append(tl.render_fact(f) + mark)
    return "<data>" + "\n".join(lines) + "</data>"


@tool
def get_shop_policy(topic: str = "all", as_of: str = "", config: RunnableConfig = None) -> str:
    """Shop policies and promotions that apply on a date (default today). `topic` is one of
    returns, shipping, promos, all. Also lists upcoming (future-dated) changes."""
    d = _valid_date(as_of) or tl.today()
    topic = topic.lower()
    prefixes = {"returns": ["policy:returns"], "shipping": ["policy:shipping"],
                "promos": ["promo:"], "all": ["policy:", "promo:"]}.get(topic, ["policy:", "promo:"])
    with tx() as c:
        every = rows(c, "SELECT * FROM edges WHERE owner=:o ORDER BY subject, relation, valid_from", o=tl.SHOP)
    lines = []
    for f in every:
        if not any(f["subject"].startswith(p) for p in prefixes):
            continue
        if tl.is_valid_on(f, d):
            lines.append(tl.render_fact(f) + f"  <-- APPLIES on {d}")
        elif f["valid_from"] > d:
            lines.append(tl.render_fact(f) + "  (upcoming, not yet in effect)")
        elif f["valid_to"] is None or f["valid_to"] < d:
            lines.append(tl.render_fact(f) + "  (superseded/expired - do not cite as current)")
    return "<data>" + ("\n".join(lines) or "No policy facts found.") + "</data>"


class OrderItem(BaseModel):
    product_id: int = Field(description="Catalogue id, e.g. 3")
    qty: int = Field(default=1, ge=1, le=20)


@tool
def place_order(items: list[OrderItem], config: RunnableConfig = None) -> str:
    """Propose an order for the CURRENT user. This does NOT place it: it validates stock/prices and
    stores a pending order. After calling, show the summary and ask the user to reply 'confirm'."""
    user_id, thread_id = _ids(config)
    try:
        quote = od.propose_order(user_id, thread_id, [i.model_dump() for i in items])
    except ValueError as e:
        return f"<data>ORDER_NOT_POSSIBLE: {e}</data>"
    lines = "; ".join(f"{l['qty']}x {l['name']} @ ${l['unit_price']:.2f} [F{l['price_fact']}]" for l in quote["lines"])
    ship = od.free_shipping_threshold()
    return (f"<data>PENDING_CONFIRMATION (nothing is ordered yet): {lines}. Subtotal ${quote['subtotal']:.2f}. "
            f"Free shipping over ${ship:.0f}. Ask the user to reply 'confirm' to place it, or 'cancel'.</data>")


@tool
def get_my_orders(config: RunnableConfig = None) -> str:
    """List the current user's recent orders."""
    user_id, _ = _ids(config)
    os_ = od.orders_for_user(user_id)
    if not os_:
        return "<data>You have no orders yet.</data>"
    out = []
    for o in os_:
        items = ", ".join(f"{l['qty']}x {l['name']}" for l in json.loads(o["items_json"]))
        out.append(f"Order #{o['id']} {o['created_at'][:10]} {o['status']} ${o['total']:.2f}: {items}")
    return "<data>" + "\n".join(out) + "</data>"


TOOLS = [search_products, get_price_history, get_shop_policy, place_order, get_my_orders]
