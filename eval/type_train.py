"""Train the type model (petey/validate/type_model.py) on the tuning set: every box the light path drew
(runs/benchmark/dev_predictions/light) that matches a key field, its features from the page, the label whether the
key field is a choice box. Logistic regression in numpy, five folds by form, the cut for the best accuracy on the
boxes the finder typed wrong as well as overall; fitted on everything and pasted with --paste. Read-only otherwise.

    PYTHONPATH=. venv/bin/python eval/type_train.py [--key DIR --pred DIR] [--paste]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
import printed_train as PT   # noqa: E402

VOCAB_SIZE = 100


def rows(key_dir: Path, pred_dir: Path) -> list[dict]:
    import pymupdf
    import benchmark_score as BS
    from petey.validate import type_model as tm
    out = []
    for x in json.loads((key_dir / "index.json").read_text()):
        pid = x["page_id"]
        key = json.loads((key_dir / f"{pid}.json").read_text())
        pf = pred_dir / "light" / f"{pid}.json"
        if not pf.exists():
            continue
        pred = BS.drop_in_ignored(json.loads(pf.read_text()), key.get("ignored") or [])
        doc = pymupdf.open(str(key_dir / "pages" / f"{pid}.pdf"))
        words = doc[0].get_text("words")
        doc.close()
        k_rect = {f["id"]: f["rect"] for f in key["fields"]}
        k_kind = {f["id"]: f["kind"] for f in key["fields"]}
        boxes = [{"rect": f["rect"], "kind": f["kind"], "code": f["id"]} for f in pred["fields"]]
        m = BS.match(k_rect, {b["code"]: b["rect"] for b in boxes}, BS.IOU)
        for b in boxes:
            k = m.get(b["code"])
            if k is None:
                continue
            out.append({"form": key["form"], "page": pid, "y": int(k_kind[k] == "choice"),
                        "finder": int(b["kind"] == "choice"), "f": tm.features(b, boxes, words)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--key", type=Path, default=ROOT / "runs/benchmark/dev_key")
    ap.add_argument("--pred", type=Path, default=ROOT / "runs/benchmark/dev_predictions")
    ap.add_argument("--paste", action="store_true")
    args = ap.parse_args()
    rs = rows(args.key, args.pred)
    numeric = sorted({k for r in rs for k in r["f"] if not k.startswith("w:")})
    df = collections.Counter(k[2:] for r in rs for k in r["f"] if k.startswith("w:"))
    vocab = [t for t, n in df.most_common(VOCAB_SIZE) if n >= 5]
    X, y, cols = PT.design(rs, vocab, numeric)
    finder = np.array([r["finder"] for r in rs])
    print(f"{len(rs)} boxes, {int(y.sum())} choice, {len(cols)} features ({len(vocab)} words), "
          f"{len({r['form'] for r in rs})} forms; the finder's shape call wrong on {int((finder != y).sum())}")
    forms = sorted({r["form"] for r in rs})
    fold_of = {f: i % 5 for i, f in enumerate(forms)}
    folds = np.array([fold_of[r["form"]] for r in rs])
    p_all = np.zeros(len(rs))
    for k in range(5):
        tr, te = folds != k, folds == k
        mean, std = X[tr].mean(0), X[tr].std(0) + 1e-9
        w = PT.fit(X[tr], y[tr], mean, std)
        p_all[te] = PT.predict(X[te], w, mean, std)
    best = min((int(((p_all >= c) != (y == 1)).sum()), c) for c in np.arange(0.2, 0.95, 0.05))
    cut = best[1]
    wrong = (p_all >= cut) != (y == 1)
    print(f"folds by form: cut {cut:.2f}, wrong {int(wrong.sum())} of {len(rs)} (the finder: {int((finder != y).sum())})")
    print(f"  choice called text {int((wrong & (y == 1)).sum())} (finder {int(((finder == 0) & (y == 1)).sum())}), "
          f"text called choice {int((wrong & (y == 0)).sum())} (finder {int(((finder == 1) & (y == 0)).sum())})")
    mean, std = X.mean(0), X.std(0) + 1e-9
    w = PT.fit(X, y, mean, std)
    weights = {c: round(float(v), 5) for c, v in zip(cols, w[:-1])}
    weights["bias"] = round(float(w[-1]), 5)
    top = sorted(weights.items(), key=lambda kv: -abs(kv[1]))[:20]
    print("strongest:", ", ".join(f"{k} {v:+.2f}" for k, v in top))
    consts = {"VOCAB": tuple(vocab), "MEAN": {c: round(float(v), 5) for c, v in zip(cols, mean)},
              "STD": {c: round(float(v), 5) for c, v in zip(cols, std)}, "WEIGHTS": weights, "CUT": round(float(cut), 2)}
    if args.paste:
        p = ROOT / "petey/validate/type_model.py"
        t = p.read_text()
        head = t.split("# ---- the fitted model")[0]
        tail = t[t.index("\n\ndef score("):]
        block = ("# ---- the fitted model (eval/type_train.py pastes these) ----\n"
                 f"VOCAB: tuple = {consts['VOCAB']!r}\nMEAN: dict = {consts['MEAN']!r}\nSTD: dict = {consts['STD']!r}\n"
                 f"WEIGHTS: Optional[dict] = {consts['WEIGHTS']!r}\nCUT = {consts['CUT']}\n")
        p.write_text(head + block + tail)
        print(f"pasted into {p}")
    else:
        (ROOT / "runs/benchmark/type_model.json").write_text(json.dumps(consts, indent=1))
        print("constants -> runs/benchmark/type_model.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
