"""Benchmark runner (stdlib only, so it works against any deployed API).

  python bench/run.py --api http://localhost:8000             # ShopBot agent (M3 timeline memory + tools)
  python bench/run.py --baseline                              # plain Haiku, no tools, no memory (M0 + A0)

Writes bench/results_<mode>.json and prints a Markdown table.
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / "backend" / ".env"
SYSTEM_BASELINE = ("You are a shopping assistant for Loom & Leaf, a small handmade-goods shop selling shoes, "
                   "bags, accessories, outdoor gear and clothing. Be concise.")


def post(url: str, body: dict, headers: dict | None = None, timeout: int = 90) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def key() -> str:
    if os.getenv("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    for line in ENV.read_text().splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("no ANTHROPIC_API_KEY")


class Agent:
    def __init__(self, api: str):
        self.api = api.rstrip("/")

    def chat(self, user: str, thread: str, msg: str) -> dict:
        return post(f"{self.api}/chat", {"user_id": user, "thread_id": thread, "message": msg})


class Baseline:
    """Plain Haiku: per-thread history only, no tools, no cross-thread memory, no guards."""
    def __init__(self, model: str):
        self.model, self.k, self.hist = model, key(), {}

    def chat(self, user: str, thread: str, msg: str) -> dict:
        h = self.hist.setdefault((user, thread), [])
        h.append({"role": "user", "content": msg})
        r = post("https://api.anthropic.com/v1/messages",
                 {"model": self.model, "max_tokens": 450, "system": SYSTEM_BASELINE, "messages": h},
                 {"x-api-key": self.k, "anthropic-version": "2023-06-01"})
        text = "".join(b.get("text", "") for b in r["content"])
        h.append({"role": "assistant", "content": text})
        return {"reply": text, "tool_calls": [], "tokens": {"in": r["usage"]["input_tokens"], "out": r["usage"]["output_tokens"]}}


def check(expect: dict, res: dict) -> list[str]:
    reply, low = res["reply"], res["reply"].lower()
    tools = [t["name"] for t in res["tool_calls"]]
    fails = []
    for s in expect.get("contains", []):
        if s.lower() not in low: fails.append(f"missing '{s}'")
    if expect.get("contains_any") and not any(s.lower() in low for s in expect["contains_any"]):
        fails.append(f"none of {expect['contains_any']}")
    for s in expect.get("not_contains", []):
        if s.lower() in low: fails.append(f"forbidden '{s}'")
    for t in expect.get("tools_include", []):
        if t not in tools: fails.append(f"tool {t} not called")
    if expect.get("no_tools") and tools: fails.append(f"unexpected tools {tools}")
    for rx in expect.get("regex", []):
        if not re.search(rx, reply): fails.append(f"regex {rx}")
    return fails


def run_file(agent, path: Path, run: str) -> list[dict]:
    out = []
    for case in json.loads(path.read_text(encoding="utf-8"))["cases"]:
        users = {"A": f"bench-A-{case['id']}-{run}", "B": f"bench-B-{case['id']}-{run}"}
        fails, lat, tin, tout, tools = [], [], 0, 0, []
        for st in case["steps"]:
            t0 = time.time()
            try:
                res = agent.chat(users[st["user"]], st["thread"], st["input"])
            except Exception as e:  # network/API failure counts as a failed step
                fails.append(f"error {e}"); continue
            lat.append(time.time() - t0)
            tin += res["tokens"]["in"]; tout += res["tokens"]["out"]
            tools += [t["name"] for t in res["tool_calls"]]
            fails += check(st["expect"], res)
            print(f"  [{case['id']}] {st['input'][:60]!r} -> {res['reply'][:110]!r}", flush=True)
        out.append({"id": case["id"], "name": case["name"], "pass": not fails, "fails": fails,
                    "latency_s": round(sum(lat), 1), "tokens_in": tin, "tokens_out": tout, "tools": tools})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--model", default="claude-haiku-5-5")
    a = ap.parse_args()
    agent = Baseline(a.model) if a.baseline else Agent(a.api)
    mode = "baseline" if a.baseline else "shopbot"
    run = uuid.uuid4().hex[:5]
    if not a.baseline:  # wait for the API (cold starts on free hosting can take ~30-60s)
        for _ in range(40):
            try:
                urllib.request.urlopen(a.api.rstrip("/") + "/health", timeout=10).read(); break
            except Exception:
                time.sleep(3)
    results = {}
    for name, f in (("functional", "tests.json"), ("attacks", "tests_attacks.json")):
        print(f"== {name} ({mode})")
        results[name] = run_file(agent, ROOT / f, run)
    (ROOT / "bench" / f"results_{mode}.json").write_text(json.dumps(results, indent=2))
    print(f"\n### {mode}\n| Suite | Passed | Pass rate | Avg latency/case | Tokens in/out |\n|---|---|---|---|---|")
    for name, rs in results.items():
        p = sum(r["pass"] for r in rs)
        print(f"| {name} | {p}/{len(rs)} | {100*p/len(rs):.0f}% | {statistics.mean(r['latency_s'] for r in rs):.1f}s | "
              f"{sum(r['tokens_in'] for r in rs)}/{sum(r['tokens_out'] for r in rs)} |")
    for name, rs in results.items():
        for r in rs:
            if not r["pass"]:
                print(f"FAIL {r['id']} {r['name']}: {r['fails']}")


if __name__ == "__main__":
    main()
