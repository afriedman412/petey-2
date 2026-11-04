"""Train the printed model (petey/validate/printed_model.py) on the tuning set: every text box the light path drew
(runs/benchmark/dev_predictions/light), its features from the page's words, the label the kind of the key field it
matches (printed / text; unmatched boxes are text). Logistic regression in numpy, five folds by form (each form
scored by a model that never saw it), the cut chosen for the best F1 over the folds; then fitted on everything and
printed as the constants to paste into printed_model.py. Read-only.

    PYTHONPATH=. venv/bin/python eval/printed_train.py [--key runs/benchmark/dev_key --pred runs/benchmark/dev_predictions] [--paste]

`--paste` writes the constants into printed_model.py in place of the current ones.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

VOCAB_SIZE = 150
L2 = 1e-3
ITERS = 400


def rows(key_dir: Path, pred_dir: Path) -> list[dict]:
    import pymupdf
    import benchmark_score as BS
    from petey.validate import printed_model as pm
    out = []
    for x in json.loads((key_dir / "index.json").read_text()):
        pid = x["page_id"]
        key = json.loads((key_dir / f"{pid}.json").read_text())
        pf = pred_dir / "light" / f"{pid}.json"
        if not pf.exists():
            continue
        pred = BS.drop_in_ignored(json.loads(pf.read_text()), key.get("ignored") or [])
        doc = pymupdf.open(str(key_dir / "pages" / f"{pid}.pdf"))
        words, size = doc[0].get_text("words"), (doc[0].rect.width, doc[0].rect.height)
        doc.close()
        k_rect = {f["id"]: f["rect"] for f in key["fields"] if f["kind"] != "choice"}
        k_kind = {f["id"]: f["kind"] for f in key["fields"]}
        page = [{"rect": f["rect"], "code": f["id"]} for f in pred["fields"]]
        text = [b for b, f in zip(page, pred["fields"]) if f["kind"] != "choice"]
        m = BS.match(k_rect, {b["code"]: b["rect"] for b in text}, BS.IOU)
        for b in text:
            out.append({"form": key["form"], "page": pid, "code": b["code"],
                        "y": int(k_kind.get(m.get(b["code"])) == "printed"), "f": pm.features(b, words, page, size)})
    return out


def design(rs: list[dict], vocab: list[str], numeric: list[str]):
    cols = numeric + [f"w:{t}" for t in vocab]
    X = np.array([[r["f"].get(c, 0.0) for c in cols] for r in rs], dtype=float)
    y = np.array([r["y"] for r in rs], dtype=float)
    return X, y, cols


def fit(X: np.ndarray, y: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    Z = (X - mean) / std
    Z = np.hstack([Z, np.ones((len(Z), 1))])
    w = np.zeros(Z.shape[1])
    pos = y.mean()
    cw = np.where(y == 1, 0.5 / max(pos, 1e-6), 0.5 / max(1 - pos, 1e-6))   # balanced classes
    lr = 0.5
    for _ in range(ITERS):
        p = 1 / (1 + np.exp(-Z @ w))
        g = Z.T @ ((p - y) * cw) / len(y) + L2 * np.append(w[:-1], 0.0)
        w -= lr * g
    return w


def predict(X: np.ndarray, w: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    Z = np.hstack([(X - mean) / std, np.ones((len(X), 1))])
    return 1 / (1 + np.exp(-Z @ w))


def prf(y: np.ndarray, p: np.ndarray, cut: float) -> tuple[float, float, float]:
    hit = float(((p >= cut) & (y == 1)).sum())
    found, key = float((p >= cut).sum()), float((y == 1).sum())
    pr, rc = hit / max(found, 1), hit / max(key, 1)
    return pr, rc, 2 * pr * rc / max(pr + rc, 1e-9)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--key", type=Path, default=ROOT / "runs/benchmark/dev_key")
    ap.add_argument("--pred", type=Path, default=ROOT / "runs/benchmark/dev_predictions")
    ap.add_argument("--paste", action="store_true")
    args = ap.parse_args()
    rs = rows(args.key, args.pred)
    numeric = sorted({k for r in rs for k in r["f"] if not k.startswith("w:")})
    df = collections.Counter(k[2:] for r in rs for k in r["f"] if k.startswith("w:"))
    dfp = collections.Counter(k[2:] for r in rs if r["y"] for k in r["f"] if k.startswith("w:"))
    vocab = [t for t, _ in sorted(df.items(), key=lambda kv: -(dfp[kv[0]] * 20 + kv[1]))[:VOCAB_SIZE] if df[t] >= 5]
    X, y, cols = design(rs, vocab, numeric)
    print(f"{len(rs)} boxes, {int(y.sum())} printed, {len(cols)} features ({len(vocab)} words), "
          f"{len({r['form'] for r in rs})} forms")
    forms = sorted({r["form"] for r in rs})
    fold_of = {f: i % 5 for i, f in enumerate(forms)}
    folds = np.array([fold_of[r["form"]] for r in rs])
    p_all = np.zeros(len(rs))
    for k in range(5):
        tr, te = folds != k, folds == k
        mean, std = X[tr].mean(0), X[tr].std(0) + 1e-9
        w = fit(X[tr], y[tr], mean, std)
        p_all[te] = predict(X[te], w, mean, std)
    best = max((prf(y, p_all, c) + (c,) for c in np.arange(0.2, 0.95, 0.05)), key=lambda t: t[2])
    print(f"folds by form: best cut {best[3]:.2f}  P {best[0]:.1%}  R {best[1]:.1%}  F1 {best[2]:.1%}")
    for c in (0.5, best[3]):
        pr, rc, f1 = prf(y, p_all, c)
        print(f"  cut {c:.2f}: P {pr:.1%}  R {rc:.1%}  F1 {f1:.1%}")
    mean, std = X.mean(0), X.std(0) + 1e-9
    w = fit(X, y, mean, std)
    weights = {c: round(float(v), 5) for c, v in zip(cols, w[:-1])}
    weights["bias"] = round(float(w[-1]), 5)
    top = sorted(weights.items(), key=lambda kv: -abs(kv[1]))[:25]
    print("strongest:", ", ".join(f"{k} {v:+.2f}" for k, v in top))
    consts = {"VOCAB": tuple(vocab), "MEAN": {c: round(float(m), 5) for c, m in zip(cols, mean)},
              "STD": {c: round(float(s), 5) for c, s in zip(cols, std)}, "WEIGHTS": weights, "CUT": round(float(best[3]), 2)}
    if args.paste:
        p = ROOT / "petey/validate/printed_model.py"
        t = p.read_text()
        head = t.split("# ---- the fitted model")[0]
        tail = t[t.index("\n\ndef score("):]
        block = ("# ---- the fitted model (eval/printed_train.py pastes these) ----\n"
                 f"VOCAB: tuple = {consts['VOCAB']!r}\nMEAN: dict = {consts['MEAN']!r}\nSTD: dict = {consts['STD']!r}\n"
                 f"WEIGHTS: Optional[dict] = {consts['WEIGHTS']!r}\nCUT = {consts['CUT']}\n")
        p.write_text(head + block + tail)
        print(f"pasted into {p}")
    else:
        (ROOT / "runs/benchmark/printed_model.json").write_text(json.dumps(consts, indent=1))
        print("constants -> runs/benchmark/printed_model.json (use --paste to write them into the module)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
