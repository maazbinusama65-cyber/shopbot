"""Stage 2 of A2: DPO on (chosen = correct dated citation, rejected = superseded/wrong citation).
The reference model is the SFT-merged model (the LoRA adapter is disabled to obtain it)."""
import torch
from datasets import Dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import DPOConfig, DPOTrainer

from common import BF16, FP16, HAS_CUDA, MODE, OUT, chat_prompt, load, model_kwargs, subset

SFT = str(OUT / "sft_merged")
tok = AutoTokenizer.from_pretrained(SFT)
rows = subset(load("dpo"), "DPO_N")
print("mode:", MODE, "| pairs:", len(rows))
ds = Dataset.from_list([{"prompt": chat_prompt(tok, r), "chosen": r["chosen"] + tok.eos_token,
                         "rejected": r["rejected"] + tok.eos_token} for r in rows])

model = AutoModelForCausalLM.from_pretrained(SFT, **model_kwargs())
lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                  target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
cfg = DPOConfig(output_dir=str(OUT / "dpo_run"), num_train_epochs=1, per_device_train_batch_size=2,
                gradient_accumulation_steps=8, learning_rate=5e-6 * 10, beta=0.1, lr_scheduler_type="cosine",
                warmup_steps=0.1, logging_steps=5, save_strategy="no", bf16=BF16, fp16=FP16, use_cpu=not HAS_CUDA, gradient_checkpointing=HAS_CUDA,
                max_length=768, report_to="none")
trainer = DPOTrainer(model=model, ref_model=None, args=cfg, train_dataset=ds, processing_class=tok,
                     peft_config=lora)
trainer.train()
trainer.model.save_pretrained(OUT / "dpo_adapter")
print("saved", OUT / "dpo_adapter")
