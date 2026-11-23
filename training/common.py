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


import os
import torch

HAS_CUDA = torch.cuda.is_available()
MODE = "QLoRA (4-bit NF4)" if HAS_CUDA else "LoRA on CPU (no CUDA available: not quantized)"


def model_kwargs() -> dict:
    """4-bit QLoRA on a GPU; plain fp32 LoRA on CPU (bitsandbytes needs CUDA)."""
    if HAS_CUDA:
        return {"quantization_config": bnb_config(), "device_map": {"": 0}, "torch_dtype": torch.bfloat16}
    return {"torch_dtype": torch.float32}


def subset(rows: list, env: str) -> list:
    n = int(os.getenv(env, "0")) or len(rows)
    return rows[:n]
