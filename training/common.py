import json
from pathlib import Path

BASE = "Qwen/Qwen2.5-0.5B-Instruct"
HERE = Path(__file__).parent
OUT = HERE / "outputs"


def load(name: str) -> list[dict]:
    return [json.loads(l) for l in (HERE / "data" / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]


def chat_prompt(tok, row: dict) -> str:
    msgs = [{"role": "system", "content": row["system"]}, {"role": "user", "content": row["prompt"]}]
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def bnb_config():
    import torch
    from transformers import BitsAndBytesConfig
    return BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                              bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
