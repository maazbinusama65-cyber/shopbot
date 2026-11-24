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
    from transformers import BitsAndBytesConfig
    return BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                              bnb_4bit_compute_dtype=DTYPE, bnb_4bit_use_double_quant=True)


import os
import torch

HAS_CUDA = torch.cuda.is_available()
CAP = torch.cuda.get_device_capability(0) if HAS_CUDA else (0, 0)
BF16 = HAS_CUDA and CAP[0] >= 8                      # T4 (7.5) has no bf16 -> use fp16 there
FP16 = HAS_CUDA and not BF16
DTYPE = torch.bfloat16 if BF16 else (torch.float16 if FP16 else torch.float32)
if HAS_CUDA and CAP[0] < 8:
    # TRL's chunked-logprob kernel uses addmm(out_dtype=fp32), which needs compute capability >= 8.0.
    # Its own fallback path works on older GPUs; force it.
    import trl.kernels.chunked_logprob as _clp
    _clp._MM_OUT_DTYPE = False
MODE = "QLoRA (4-bit NF4)" if HAS_CUDA else "LoRA on CPU (no CUDA available: not quantized)"


def model_kwargs() -> dict:
    """4-bit QLoRA on a GPU; plain fp32 LoRA on CPU (bitsandbytes needs CUDA)."""
    if HAS_CUDA:
        return {"quantization_config": bnb_config(), "device_map": {"": 0}, "torch_dtype": DTYPE}
    return {"torch_dtype": torch.float32}


def subset(rows: list, env: str) -> list:
    n = int(os.getenv(env, "0")) or len(rows)
    return rows[:n]
