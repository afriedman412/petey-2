"""Train `petey.label.text_match`: a cross-encoder over (text, field) pairs from `eval/text_match_data.py`, then
export it to ONNX for onnxruntime. Runs in the training venv (PyTorch, transformers), not the project venv, and
imports nothing from petey.

    ~/Documents/code/.venvs/petey-train/bin/python eval/text_match_train.py [--epochs 2] [--limit N]

Start: `cross-encoder/ms-marco-MiniLM-L6-v2` (22M parameters, already a relevance scorer). Loss: binary
cross-entropy on the pair's label. Caption pairs are few next to name pairs, so they are repeated (`--caption-x`).
A twentieth of the training forms is kept aside as a dev set for the loss printed each half epoch; the test
forms are never read here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "runs" / "text_match"
OUT = REPO / "models" / "text_match"
BASE = "cross-encoder/ms-marco-MiniLM-L6-v2"
MAX_LEN = 96


def pairs(path: Path, caption_x: int) -> list[tuple[str, str, float, str]]:
    out = []
    for line in path.open():
        r = json.loads(line)
        if r["kind"] == "caption":
            for _ in range(caption_x):
                out.append((r["caption"], r["option"], 1.0, r["form"]))
                out += [(w, r["option"], 0.0, r["form"]) for w in r["wrong"]]
        else:
            out.append((r["text"], r["field"], float(r["label"]), r["form"]))
    return out


def dev_form(form: str) -> bool:
    return int(hashlib.sha1(("dev" + form).encode()).hexdigest(), 16) % 20 == 0


def batches(rows, size, tok, device, shuffle):
    idx = list(range(len(rows)))
    if shuffle:
        random.shuffle(idx)
    for i in range(0, len(idx), size):
        chunk = [rows[j] for j in idx[i:i + size]]
        enc = tok([c[0] for c in chunk], [c[1] for c in chunk], truncation=True, max_length=MAX_LEN,
                  padding=True, return_tensors="pt")
        yield {k: v.to(device) for k, v in enc.items()}, torch.tensor([c[2] for c in chunk], device=device)


@torch.no_grad()
def dev_loss(model, rows, tok, device) -> float:
    model.eval()
    loss_fn = torch.nn.BCEWithLogitsLoss(reduction="sum")
    total = 0.0
    for enc, y in batches(rows, 256, tok, device, False):
        total += loss_fn(model(**enc).logits.view(-1), y).item()
    model.train()
    return total / max(len(rows), 1)


def export_onnx() -> None:
    """ONNX from the saved weights. The inputs go in the order of the model's forward() (input_ids,
    attention_mask, token_type_ids), not the tokenizer's: exported by position in the tokenizer's order the mask
    and the segment ids trade places and every score is wrong (2026-10-09: +2.8 against PyTorch's -2.1)."""
    tok = AutoTokenizer.from_pretrained(OUT / "hf")
    model = AutoModelForSequenceClassification.from_pretrained(OUT / "hf", attn_implementation="eager").eval()
    enc = tok(["a short text", "a somewhat longer text to pad against"], ["a field", "another field name here"],
              padding=True, return_tensors="pt")
    names = [k for k in ("input_ids", "attention_mask", "token_type_ids") if k in enc]
    torch.onnx.export(model, tuple(enc[k] for k in names), str(OUT / "model.onnx"), input_names=names,
                      output_names=["logits"], dynamic_axes={k: {0: "batch", 1: "seq"} for k in names} |
                      {"logits": {0: "batch"}}, opset_version=17, dynamo=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--caption-x", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="train on this many pairs only (a smoke run)")
    ap.add_argument("--export-only", action="store_true", help="re-export models/text_match/hf to ONNX")
    args = ap.parse_args()
    if args.export_only:
        export_onnx()
        return 0
    random.seed(7)
    torch.manual_seed(7)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    rows = pairs(DATA / "train.jsonl", args.caption_x)
    dev = [r for r in rows if dev_form(r[3])]
    train = [r for r in rows if not dev_form(r[3])]
    random.shuffle(train)
    if args.limit:
        train = train[:args.limit]
    dev = random.sample(dev, min(len(dev), 8000))
    print(f"train {len(train)} pairs ({sum(r[2] for r in train):.0f} positive), dev {len(dev)}, device {device}")
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForSequenceClassification.from_pretrained(BASE, num_labels=1).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = args.epochs * ((len(train) + args.batch - 1) // args.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=steps, pct_start=0.06)
    loss_fn = torch.nn.BCEWithLogitsLoss()
    print(f"dev loss before: {dev_loss(model, dev, tok, device):.4f}", flush=True)
    t0, step = time.time(), 0
    for ep in range(args.epochs):
        for enc, y in batches(train, args.batch, tok, device, True):
            loss = loss_fn(model(**enc).logits.view(-1), y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            step += 1
            if step % 200 == 0:
                rate = step * args.batch / (time.time() - t0)
                print(f"  step {step}/{steps}  loss {loss.item():.4f}  {rate:.0f} pairs/s  "
                      f"eta {(steps - step) * args.batch / rate / 60:.1f} min", flush=True)
            if step % max(steps // (2 * args.epochs), 1) == 0:
                print(f"  dev loss {dev_loss(model, dev, tok, device):.4f}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUT / "hf")
    tok.save_pretrained(OUT / "hf")
    tok.backend_tokenizer.save(str(OUT / "tokenizer.json"))
    export_onnx()
    (OUT / "meta.json").write_text(json.dumps({"base": BASE, "epochs": args.epochs, "pairs": len(train),
                                               "caption_x": args.caption_x, "lr": args.lr,
                                               "trained": time.strftime("%Y-%m-%d %H:%M")}, indent=1))
    print(f"wrote {OUT}  ({(time.time() - t0) / 60:.1f} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
