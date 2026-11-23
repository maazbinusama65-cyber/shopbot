from app import timeline as tl


def test_price_history_is_kept_and_as_of_picks_right_edge():
    # product 1: 89 until 2026-09-30, 79 from 2026-10-01 (seed)
    old = tl.facts_as_of(tl.SHOP, "2026-09-15", "product:1", "price")
    new = tl.facts_as_of(tl.SHOP, "2026-11-23", "product:1", "price")
    assert [f["object"] for f in old] == ["89.0"]
    assert [f["object"] for f in new] == ["79.0"]
    assert len(tl.history(tl.SHOP, "product:1", "price")) == 2


def test_exclusive_write_closes_previous_edge_without_deleting():
    tl.add_fact("u-t1", "user:u-t1", "size", "9", valid_from="2026-01-01")
    tl.add_fact("u-t1", "user:u-t1", "size", "10", valid_from="2026-06-01")
    h = tl.history("u-t1", "user:u-t1", "size")
    assert [(f["object"], f["valid_to"]) for f in h] == [("9", "2026-05-31"), ("10", None)]
    assert [f["object"] for f in tl.facts_as_of("u-t1", "2026-03-01", relation="size")] == ["9"]


def test_same_value_is_idempotent():
    a = tl.add_fact("u-t2", "user:u-t2", "likes", "wool")
    b = tl.add_fact("u-t2", "user:u-t2", "likes", "wool")
    assert a == b


def test_future_dated_promo_not_active_today_but_active_on_date():
    assert tl.facts_as_of(tl.SHOP, "2026-11-23", "promo:black-friday", "discount_pct") == []
    assert tl.facts_as_of(tl.SHOP, "2026-11-28", "promo:black-friday", "discount_pct")


def test_current_price_applies_discount_on_promo_day_only():
    base, _ = tl.current_price(1, "2026-11-23")
    # promo is attached to promo:black-friday, not products, so product price is unchanged
    assert base == 79.0


def test_user_facts_are_scoped_by_owner():
    tl.add_fact("alice", "user:alice", "name", "Alice")
    tl.add_fact("bob", "user:bob", "name", "Bob")
    assert [f["object"] for f in tl.user_profile("alice")] == ["Alice"]
    assert tl.get_fact("bob", tl.user_profile("alice")[0]["id"]) is None
