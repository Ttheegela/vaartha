"""
amarel_score_gdelt.py — GeoSentinel Terminal (VARTA)
Scores all GDELT headlines for geopolitical supply chain crisis risk using
Gemma 4 27B via HuggingFace transformers. Designed to run on Amarel GPU nodes.

Usage (on Amarel compute node, inside conda env):
    python amarel_score_gdelt.py --input gdelt.parquet --output gdelt_scored.parquet

Output: parquet with llm_score column (float 0.0–1.0) filled for all rows.
"""

import argparse
import json
import re
import sys
import time
import warnings
from pathlib import Path

import polars as pl
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

warnings.filterwarnings("ignore")

# ── CLI args ──────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--input",  required=True, help="Path to gdelt.parquet")
parser.add_argument("--output", required=True, help="Path to write gdelt_scored.parquet")
parser.add_argument("--model",  default="google/gemma-4-26B-A4B-it", help="HuggingFace model ID")
parser.add_argument("--batch",  type=int, default=8, help="Batch size (default 8)")
args = parser.parse_args()

# ── Load model ────────────────────────────────────────────────────────────────
print(f"Loading {args.model} with device_map='auto'...")
print(f"Available GPUs: {torch.cuda.device_count()}")
for i in range(torch.cuda.device_count()):
    props = torch.cuda.get_device_properties(i)
    print(f"  GPU {i}: {props.name} — {props.total_memory // 1024**3}GB VRAM")

tokenizer = AutoTokenizer.from_pretrained(args.model)
model = AutoModelForCausalLM.from_pretrained(
    args.model,
    device_map="auto",
    torch_dtype=torch.bfloat16,
)
model.eval()
print("Model loaded.\n")

# ── Prompt builder ────────────────────────────────────────────────────────────
SYSTEM = (
    "You are a geopolitical supply chain risk analyst. "
    "Score headlines for crisis risk considering: trade wars, sanctions, "
    "critical mineral supply disruptions, semiconductor supply chain, "
    "energy supply shocks, shipping route disruptions, and military conflicts."
)

OUTPUT_SCHEMA = {
    "crisis_score": "float 0.0-1.0: probability this headline signals a geopolitical supply chain crisis",
    "sentiment":    "string: negative | neutral | positive",
    "key_entities": "list of strings: countries, assets, or events mentioned",
    "reasoning":    "string: one sentence justification",
}


def build_prompt(headline: str) -> str:
    """Build instruction prompt for a single headline."""
    return (
        f"<start_of_turn>user\n"
        f"{SYSTEM}\n\n"
        f"Score this headline. Return ONLY valid JSON matching: {json.dumps(OUTPUT_SCHEMA)}\n\n"
        f"Headline: {headline}<end_of_turn>\n"
        f"<start_of_turn>model\n"
    )


def extract_score(text: str) -> float:
    """
    Parse crisis_score from model output. Falls back to 0.5 on parse failure.

    Args:
        text: Raw model output string.
    Returns:
        Float crisis score between 0.0 and 1.0.
    """
    try:
        # Strip markdown code fences if present
        clean = re.sub(r"```(?:json)?", "", text).strip()
        # Find JSON object
        match = re.search(r"\{.*?\}", clean, re.DOTALL)
        if match:
            data = json.loads(match.group())
            score = float(data.get("crisis_score", 0.5))
            return max(0.0, min(1.0, score))
    except Exception:
        pass
    return 0.5


# ── Load data ─────────────────────────────────────────────────────────────────
print(f"Loading {args.input}...")
df = pl.read_parquet(args.input)
headlines = df["headline"].to_list()
total = len(headlines)
print(f"Total headlines to score: {total:,}\n")

# ── Score in batches ──────────────────────────────────────────────────────────
scores = []
batch_size = args.batch
start_time = time.time()

for batch_start in range(0, total, batch_size):
    batch_headlines = headlines[batch_start: batch_start + batch_size]
    prompts = [build_prompt(h) for h in batch_headlines]

    inputs = tokenizer(
        prompts,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=512,
    ).to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=128,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )

    for i, output in enumerate(outputs):
        input_len = inputs["input_ids"].shape[1]
        new_tokens = output[input_len:]
        text = tokenizer.decode(new_tokens, skip_special_tokens=True)
        scores.append(extract_score(text))

    # Progress log every 10 batches
    scored = min(batch_start + batch_size, total)
    if (batch_start // batch_size) % 10 == 0:
        elapsed = time.time() - start_time
        rate = scored / elapsed if elapsed > 0 else 0
        eta = (total - scored) / rate if rate > 0 else 0
        print(
            f"  [{scored:>5}/{total}] "
            f"{scored/total*100:.1f}% — "
            f"{rate:.1f} headlines/s — "
            f"ETA: {eta/60:.0f} min"
        )
        sys.stdout.flush()

elapsed_total = time.time() - start_time
print(f"\nScoring complete — {total:,} headlines in {elapsed_total/60:.1f} min")
print(f"Mean crisis score: {sum(scores)/len(scores):.3f}")

# ── Save ──────────────────────────────────────────────────────────────────────
df_scored = df.with_columns(pl.Series("llm_score", scores))
df_scored.write_parquet(args.output)
print(f"Saved → {args.output} ({len(df_scored):,} rows)")
