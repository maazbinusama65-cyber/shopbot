"""M3 timeline memory: a dated graph of facts.

Every fact is an edge (subject --relation--> object) valid over [valid_from, valid_to].
`valid_to IS NULL` means "still true". Writing a new value for an *exclusive* relation
closes the previous edge instead of overwriting it, so history is never lost and the agent
can answer "what applied on date X?".

`owner` is either SHOP (global facts: prices, policies, promos) or a user_id (private facts).
Every read/write takes `owner` explicitly and the agent tools take it from the request
config, never from model-supplied arguments, so one user can never read another's edges.
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from .db import insert_returning_id, one, rows, tx

SHOP = "shop"

# Relations where a new value replaces the old one (history is kept, old edge is closed).
EXCLUSIVE = {"price", "discount_pct", "window_days", "free_over", "name", "budget",
             "size", "city", "delivery_days", "status"}


def today() -> str:
    return date.today().isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse(d: str) -> date:
    return date.fromisoformat(d)


def add_fact(owner: str, subject: str, relation: str, obj: str,
             valid_from: str | None = None, valid_to: str | None = None,
             source: str = "") -> int:
    """Insert a fact. For exclusive relations, close any open edge that this one supersedes."""
    valid_from = valid_from or today()
    obj = str(obj)
    with tx() as c:
        dup = one(c, "SELECT id FROM edges WHERE owner=:o AND subject=:s AND relation=:r AND object=:b "
                     "AND (valid_from=:vf OR valid_to IS NULL)", o=owner, s=subject, r=relation,
                  b=obj, vf=valid_from)
        if dup:
            return dup["id"]
        if relation in EXCLUSIVE and valid_to is None:
            open_edges = rows(
                c, "SELECT id, valid_from, object FROM edges WHERE owner=:o AND subject=:s "
                   "AND relation=:r AND valid_to IS NULL", o=owner, s=subject, r=relation)
            for e in open_edges:
                if e["object"] == obj:
                    return e["id"]  # idempotent: same value already open
                close_on = _parse(valid_from) - timedelta(days=1)
                if close_on < _parse(e["valid_from"]):
                    # same-day (or retroactive) correction: the old edge never applied
                    c.execute(text("DELETE FROM edges WHERE id=:i"), {"i": e["id"]})
                else:
                    c.execute(text("UPDATE edges SET valid_to=:v WHERE id=:i"),
                              {"v": close_on.isoformat(), "i": e["id"]})
        return insert_returning_id(
            c, "INSERT INTO edges(owner,subject,relation,object,valid_from,valid_to,source,created_at) "
               "VALUES(:o,:s,:r,:obj,:vf,:vt,:src,:ca)",
            o=owner, s=subject, r=relation, obj=obj, vf=valid_from, vt=valid_to,
            src=source, ca=_now())


def facts_as_of(owner: str, as_of: str | None = None, subject: str | None = None,
                relation: str | None = None) -> list[dict]:
    """Facts that were true on `as_of` (default: today)."""
    as_of = as_of or today()
    sql = ("SELECT * FROM edges WHERE owner=:o AND valid_from<=:d "
           "AND (valid_to IS NULL OR valid_to>=:d)")
    params: dict = {"o": owner, "d": as_of}
    if subject:
        sql += " AND subject=:s"
        params["s"] = subject
    if relation:
        sql += " AND relation=:r"
        params["r"] = relation
    with tx() as c:
        return rows(c, sql + " ORDER BY subject, relation, valid_from", **params)


def history(owner: str, subject: str, relation: str | None = None) -> list[dict]:
    sql = "SELECT * FROM edges WHERE owner=:o AND subject=:s"
    params: dict = {"o": owner, "s": subject}
    if relation:
        sql += " AND relation=:r"
        params["r"] = relation
    with tx() as c:
        return rows(c, sql + " ORDER BY relation, valid_from", **params)


def get_fact(owner: str, fact_id: int) -> dict | None:
    with tx() as c:
        return one(c, "SELECT * FROM edges WHERE id=:i AND owner=:o", i=fact_id, o=owner)


def is_valid_on(fact: dict, as_of: str) -> bool:
    return fact["valid_from"] <= as_of and (fact["valid_to"] is None or fact["valid_to"] >= as_of)


def current_price(product_id: int, as_of: str | None = None) -> tuple[float, int] | None:
    """(price after any active percentage discount, fact id of the base price) or None."""
    as_of = as_of or today()
    subj = f"product:{product_id}"
    base = facts_as_of(SHOP, as_of, subj, "price")
    if not base:
        return None
    price = float(base[0]["object"])
    for d in facts_as_of(SHOP, as_of, subj, "discount_pct"):
        price = round(price * (1 - float(d["object"]) / 100), 2)
    return price, base[0]["id"]


def render_fact(f: dict) -> str:
    end = f["valid_to"] or "now"
    return f"[F{f['id']}] {f['subject']} {f['relation']}={f['object']} (valid {f['valid_from']}..{end})"


def user_profile(user_id: str, limit: int = 12) -> list[dict]:
    """Currently valid private facts about this user (for prompt injection)."""
    out = [f for f in facts_as_of(user_id, subject=f"user:{user_id}")]
    return out[-limit:]
