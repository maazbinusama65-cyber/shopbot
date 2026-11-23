"""Stage 1 of A2: QLoRA supervised fine-tuning on (dated facts + question) -> correct cited answer."""
import torch
from datasets import Dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

from common import BASE, OUT, bnb_config, chat_prompt, load

tok = AutoTokenizer.from_pretrained(BASE)
rows = load("sft")
ds = Dataset.from_list([{"text": chat_prompt(tok, r) + r["chosen"] + tok.eos_token} for r in rows])

model = AutoModelForCausalLM.from_pretrained(BASE, quantization_config=bnb_config(), device_map={"": 0},
                                             torch_dtype=torch.bfloat16)
lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                  target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
cfg = SFTConfig(output_dir=str(OUT / "sft_run"), num_train_epochs=2, per_device_train_batch_size=4,
                gradient_accumulation_steps=4, learning_rate=2e-4, lr_scheduler_type="cosine", warmup_ratio=0.05,
                logging_steps=10, save_strategy="no", bf16=True, gradient_checkpointing=True,
                max_length=768, dataset_text_field="text", report_to="none")
trainer = SFTTrainer(model=model, args=cfg, train_dataset=ds, peft_config=lora, processing_class=tok)
trainer.train()
trainer.model.save_pretrained(OUT / "sft_adapter")

# Merge the adapter into a full-precision copy: it becomes the reference model for DPO.
del trainer, model
torch.cuda.empty_cache()
from peft import PeftModel
base = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16)
merged = PeftModel.from_pretrained(base, OUT / "sft_adapter").merge_and_unload()
merged.save_pretrained(OUT / "sft_merged")
tok.save_pretrained(OUT / "sft_merged")
print("saved", OUT / "sft_adapter", "and", OUT / "sft_merged")
