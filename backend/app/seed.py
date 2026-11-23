"""Demo data: a small handmade-goods shop with a price/policy history so the timeline matters."""
from sqlalchemy import text

from . import timeline as tl
from .db import init_schema, insert_returning_id, tx

SHOP_NAME = "Loom & Leaf"

# (name, category, description, stock, current price, previous price, price change date)
PRODUCTS = [
    ("Trail Runner Shoes", "shoes", "Lightweight running shoes, sizes 6-13, grippy outsole.", 25, 79.0, 89.0, "2026-10-01"),
    ("Canvas Sneakers", "shoes", "Everyday low-top canvas sneakers in white or black.", 40, 49.0, None, None),
    ("Leather Weekender Bag", "bags", "Full-grain leather duffel, 38L, brass hardware.", 8, 189.0, 169.0, "2026-09-15"),
    ("Everyday Tote", "bags", "Waxed canvas tote with inner zip pocket.", 30, 39.0, None, None),
    ("Merino Beanie", "accessories", "Soft merino wool beanie, one size.", 60, 24.0, None, None),
    ("Wool Scarf", "accessories", "Long woven wool scarf, charcoal or oat.", 35, 34.0, 29.0, "2026-11-01"),
    ("Stainless Water Bottle", "outdoor", "750ml insulated bottle, keeps cold 24h.", 80, 27.0, None, None),
    ("Camp Mug Set", "outdoor", "Set of 2 enamel camp mugs.", 3, 22.0, None, None),
    ("Linen Shirt", "clothing", "Relaxed-fit linen shirt, sizes S-XL.", 20, 58.0, 64.0, "2026-10-20"),
    ("Chino Shorts", "clothing", "Stretch cotton chino shorts, sizes 28-38.", 0, 45.0, None, None),
    ("Silk Sleep Mask", "accessories", "100% mulberry silk sleep mask.", 50, 18.0, None, None),
    ("Hiking Socks (3-pack)", "outdoor", "Cushioned merino blend hiking socks.", 70, 21.0, None, None),
]


def seed(force: bool = False) -> None:
    init_schema()
    with tx() as c:
        n = c.execute(text("SELECT COUNT(*) FROM products")).scalar_one()
        if n and not force:
            return
    for name, cat, desc, stock, price, prev, changed in PRODUCTS:
        with tx() as c:
            pid = insert_returning_id(
                c, "INSERT INTO products(name,category,description,stock,active,created_at) "
                   "VALUES(:n,:c,:d,:s,1,:t)", n=name, c=cat, d=desc, s=stock, t=tl.today())
        subj = f"product:{pid}"
        if prev is not None:
            tl.add_fact(tl.SHOP, subj, "price", str(prev), valid_from="2026-01-01", source="seed")
        tl.add_fact(tl.SHOP, subj, "price", str(price), valid_from=changed or "2026-01-01", source="seed")

    # Policies with history, plus a dated future promo.
    tl.add_fact(tl.SHOP, "policy:returns", "window_days", "14", valid_from="2026-01-01", source="policy")
    tl.add_fact(tl.SHOP, "policy:returns", "window_days", "30", valid_from="2026-11-01", source="policy")
    tl.add_fact(tl.SHOP, "policy:shipping", "free_over", "50", valid_from="2026-01-01", source="policy")
    tl.add_fact(tl.SHOP, "policy:shipping", "free_over", "75", valid_from="2026-11-10", source="policy")
    tl.add_fact(tl.SHOP, "policy:shipping", "delivery_days", "3-5", valid_from="2026-01-01", source="policy")
    tl.add_fact(tl.SHOP, "promo:black-friday", "discount_pct", "20",
                valid_from="2026-11-27", valid_to="2026-11-30", source="promo")
    tl.add_fact(tl.SHOP, "promo:black-friday", "applies_to", "category:all",
                valid_from="2026-11-27", valid_to="2026-11-30", source="promo")


if __name__ == "__main__":
    seed(force=False)
    print("seeded")
