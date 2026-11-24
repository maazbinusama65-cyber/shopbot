"""Evaluate citation accuracy on the held-out set.

  python eval.py                 -> base (A0), SFT, SFT+DPO   (local models, greedy decoding)
  python eval.py --haiku 60      -> also the Haiku baseline on the first 60 eval rows (needs ANTHROPIC_API_KEY)

Metrics: cite_acc = cited fact id == the fact valid on the date; value_acc = gold value present;
         both = both right; stale_cite = cited a fact that was NOT valid on the date (the error DPO targets).
"""
import argparse
import json
import os
import re
import urllib.request

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from common import BASE, DTYPE, HERE, OUT, chat_prompt, load

CITE = re.compile(r"\[F(\d+)\]")


def score(rows: list[dict], outputs: list[str]) -> dict:
    n = len(rows)
    cite = val = both = stale = fmt = 0
    for r, o in zip(rows, outputs):
        m = CITE.findall(o)
        fmt += bool(m)
        c = bool(m) and int(m[0]) == r["gold_id"]
        v = re.search(rf"(?<![\d.]){re.escape(r['gold_value'])}(?![\d.])", o) is not None
        cite += c; val += v; both += c and v
        stale += bool(m) and int(m[0]) != r["gold_id"]
    return {"n": n, "format_ok": round(fmt / n, 3), "cite_acc": round(cite / n, 3), "value_acc": round(val / n, 3),
            "both": round(both / n, 3), "stale_cite": round(stale / n, 3)}


@torch.no_grad()
def generate(model, tok, rows: list[dict]) -> list[str]:
    outs = []
    for r in rows:
        ids = tok(chat_prompt(tok, r), return_tensors="pt").to(model.device)
        g = model.generate(**ids, max_new_tokens=24, do_sample=False, pad_token_id=tok.eos_token_id)
        outs.append(tok.decode(g[0, ids["input_ids"].shape[1]:], skip_special_tokens=True).strip())
    return outs


def haiku(rows: list[dict], key: str) -> list[str]:
    outs = []
    for r in rows:
        body = {"model": "claude-haiku-5-5", "max_tokens": 400, "system": r["system"],
                "messages": [{"role": "user", "content": r["prompt"]}]}
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", json.dumps(body).encode(),
                                     {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
        outs.append("".join(b.get("text", "") for b in json.loads(urllib.request.urlopen(req, timeout=60).read())["content"]))
    return outs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--haiku", type=int, default=0)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    rows = load("eval")[: int(os.getenv('EVAL_N', '0')) or None]
    results, samples = {}, {}
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    def run(name, model_dir, adapter=None):
        tok = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForCausalLM.from_pretrained(model_dir, torch_dtype=DTYPE).to(dev)
        if adapter:
            model = PeftModel.from_pretrained(model, adapter).merge_and_unload()
        model.eval()
        outs = generate(model, tok, rows)
        results[name], samples[name] = score(rows, outs), outs[:5]
        print(name, results[name], flush=True)
        del model
        torch.cuda.empty_cache()

    if not a.only or a.only == "base":
        run("A0 base Qwen2.5-0.5B (no fine-tune)", BASE)
    if (OUT / "sft_merged").exists() and (not a.only or a.only == "sft"):
        run("A2a QLoRA SFT", str(OUT / "sft_merged"))
    if (OUT / "dpo_adapter").exists() and (not a.only or a.only == "dpo"):
        run("A2b QLoRA SFT + DPO", str(OUT / "sft_merged"), str(OUT / "dpo_adapter"))
    if a.haiku:
        key = os.environ.get("ANTHROPIC_API_KEY") or next(
            l.split("=", 1)[1].strip() for l in (HERE.parent / "backend" / ".env").read_text().splitlines()
            if l.startswith("ANTHROPIC_API_KEY="))
        sub = rows[: a.haiku]
        outs = haiku(sub, key)
        name = f"Haiku 5.5 baseline, facts in prompt (n={a.haiku})"
        results[name], samples[name] = score(sub, outs), outs[:5]
        print(name, results[name], flush=True)
    (HERE / "eval_results.json").write_text(json.dumps({"results": results, "samples": samples}, indent=2))
    print("\n| Model | n | format ok | cite acc | value acc | both | stale-cite |\n|---|---|---|---|---|---|---|")
    for k, v in results.items():
        print(f"| {k} | {v['n']} | {v['format_ok']:.0%} | {v['cite_acc']:.0%} | {v['value_acc']:.0%} | {v['both']:.0%} | {v['stale_cite']:.0%} |")


if __name__ == "__main__":
    main()
