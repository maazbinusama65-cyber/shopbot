"""Synthetic data for A2 (QLoRA SFT -> DPO): "cite the fact that applied on the question date".

Each example shows a small dated timeline (M3 facts) and asks for a value on some date. The
answer must give the value AND cite the id of the fact that was valid on that date.
  chosen   = correct value + correct fact id
  rejected = a plausible wrong citation: a superseded / not-yet-valid fact of the same
             subject (hard negative), or the right value with the wrong id.
Run: python make_data.py   (writes data/{sft,dpo,eval}.jsonl; seeds keep the splits disjoint)
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

SYSTEM = ("You are a shop assistant. Use ONLY the dated facts given. Answer with the value that applies on the "
          "question date and cite the fact id that was valid on that date, e.g. '$79 [F12]'.")
PRODUCTS = ["Trail Runner Shoes", "Canvas Sneakers", "Leather Weekender Bag", "Everyday Tote", "Merino Beanie",
            "Wool Scarf", "Stainless Water Bottle", "Camp Mug Set", "Linen Shirt", "Chino Shorts", "Silk Sleep Mask",
            "Hiking Socks", "Denim Jacket", "Rain Poncho", "Canvas Belt", "Leather Wallet", "Sun Hat", "Wool Socks",
            "Travel Pouch", "Field Notebook", "Enamel Pin Set", "Cotton Tee", "Fleece Vest", "Trekking Poles"]
POLICIES = [("returns", "window_days", "days", [7, 14, 21, 30, 45, 60]),
            ("shipping", "free_over", "dollars", [40, 50, 60, 75, 100]),
            ("warranty", "months", "months", [3, 6, 12, 24])]
START, END = date(2026, 1, 1), date(2026, 12, 31)


def d(x: date) -> str:
    return x.isoformat()


def make_history(rng: random.Random, values: list) -> list[dict]:
    """2-3 consecutive validity windows with distinct values."""
    n = rng.choice([2, 3])
    vals = rng.sample(values, n)
    cuts = sorted(rng.sample(range(40, 320, 7), n - 1))
    starts = [START] + [START + timedelta(days=c) for c in cuts]
    out = []
    for i, v in enumerate(vals):
        to = None if i == n - 1 else d(starts[i + 1] - timedelta(days=1))
        out.append({"value": v, "from": d(starts[i]), "to": to})
    return out


def render(fid: int, subj: str, rel: str, h: dict) -> str:
    return f"[F{fid}] {subj} {rel}={h['value']} (valid {h['from']}..{h['to'] or 'now'})"


def valid_on(h: dict, day: str) -> bool:
    return h["from"] <= day and (h["to"] is None or h["to"] >= day)


def example(rng: random.Random) -> dict:
    ids = rng.sample(range(1, 400), 12)
    kind = rng.choice(["price", "price", "policy"])
    if kind == "price":
        name = rng.choice(PRODUCTS)
        subj, rel, unit = f"product:{name}", "price", "$"
        hist = make_history(rng, [round(rng.uniform(12, 220)) for _ in range(12)])
        label = f"the price of {name}"
    else:
        pol, rel, unit_name, vals = rng.choice(POLICIES)
        subj, unit = f"policy:{pol}", ""
        hist = make_history(rng, vals)
        label = f"the {pol} {rel.replace('_', ' ')}"
        unit = unit_name
    fids = ids[: len(hist)]
    facts = [render(f, subj, rel, h) for f, h in zip(fids, hist)]
    # distractors: facts about other subjects
    for f in ids[len(hist): len(hist) + rng.choice([2, 3, 4])]:
        other = rng.choice(PRODUCTS)
        h = make_history(rng, [round(rng.uniform(12, 220)) for _ in range(12)])[0]
        facts.append(render(f, f"product:{other}", "price", h))
    rng.shuffle(facts)
    today = date(2026, 11, 23)
    qday = d(START + timedelta(days=rng.randrange((today - START).days)))
    phrasing = rng.choice([f"What was {label} on {qday}?", f"On {qday}, what applied for {label}?",
                           f"As of {qday}, what is {label}?"])
    if rng.random() < 0.3:
        qday = d(today)
        phrasing = rng.choice([f"What is {label} today?", f"What is {label} right now?"])
    gold_i = next(i for i, h in enumerate(hist) if valid_on(h, qday))
    gold_id, gold_val = fids[gold_i], hist[gold_i]["value"]

    def fmt(val, fid):
        return (f"${val} [F{fid}]" if unit == "$" else f"{val} {unit} [F{fid}]")

    chosen = fmt(gold_val, gold_id)
    wrong_i = rng.choice([i for i in range(len(hist)) if i != gold_i])
    if rng.random() < 0.75:      # hard negative: another version of the same fact
        rejected = fmt(hist[wrong_i]["value"], fids[wrong_i])
    else:                        # right value, wrong id (mis-citation)
        rejected = fmt(gold_val, rng.choice([f for f in ids if f != gold_id]))
    prompt = "Facts:\n" + "\n".join(facts) + f"\n\nQuestion (today is {d(today)}): {phrasing}"
    return {"system": SYSTEM, "prompt": prompt, "chosen": chosen, "rejected": rejected,
            "gold_id": gold_id, "gold_value": str(gold_val)}


def write(path: Path, n: int, seed: int) -> None:
    rng = random.Random(seed)
    seen, rows = set(), []
    while len(rows) < n:
        ex = example(rng)
        if ex["prompt"] in seen:
            continue
        seen.add(ex["prompt"])
        rows.append(ex)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    print(f"{path}: {n} rows")


if __name__ == "__main__":
    out = Path(__file__).parent / "data"
    out.mkdir(exist_ok=True)
    write(out / "sft.jsonl", 1500, seed=1)
    write(out / "dpo.jsonl", 900, seed=2)
    write(out / "eval.jsonl", 200, seed=3)
    # sanity: no prompt overlap between train and eval
    ev = {json.loads(l)["prompt"] for l in (out / "eval.jsonl").read_text().splitlines()}
    tr = {json.loads(l)["prompt"] for f in ("sft", "dpo") for l in (out / f"{f}.jsonl").read_text().splitlines()}
    assert not (ev & tr), "train/eval leakage"
    print("no train/eval prompt overlap")
