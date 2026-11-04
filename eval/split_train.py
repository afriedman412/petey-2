"""Train the split model (petey/validate/split_model.py) on the tuning set: every pair of adjacent text boxes in a run
(compound_values._runs over the light path's boxes, runs/benchmark/dev_predictions/light), its features from the
page's words, the label whether the key puts the two boxes in one value (both matched to key fields of one split
value: 1; both matched, apart: 0; a box the key lacks: left out). Logistic regression in numpy, five folds by form,
the cut for the best F1; fitted on everything and pasted with --paste. Read-only otherwise.

    PYTHONPATH=. venv/bin/python eval/split_train.py [--key DIR --pred DIR] [--paste]
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
import printed_train as PT   # noqa: E402  fit / predict / prf

VOCAB_SIZE = 100


def rows(key_dir: Path, pred_dir: Path) -> list[dict]:
    import pymupdf
    import benchmark_score as BS
    from petey.validate import compound_values as cv
    from petey.validate import split_model as sm
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
        k_unit, _k_vals, k_kind = BS.units(key)
        k_rect = {f["id"]: f["rect"] for f in key["fields"] if f["kind"] != "choice"}
        size = collections.Counter(k_unit[f] for f in k_rect)
        page = [{"rect": f["rect"], "code": f["id"]} for f in pred["fields"]]
        text = [b for b, f in zip(page, pred["fields"]) if f["kind"] != "choice"]
        m = BS.match(k_rect, {b["code"]: b["rect"] for b in text}, BS.IOU)
        for run in cv._runs(text):
            for a, b in zip(run, run[1:]):
                ka, kb = m.get(a["code"]), m.get(b["code"])
                if ka is None or kb is None:
                    continue
                y = int(k_unit[ka] == k_unit[kb] and size[k_unit[ka]] >= 2)
                out.append({"form": key["form"], "page": pid, "y": y, "f": sm.features(a, b, run, words, page)})
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
    dfp = collections.Counter(k[2:] for r in rs if r["y"] for k in r["f"] if k.startswith("w:"))
    vocab = [t for t, _ in sorted(df.items(), key=lambda kv: -(dfp[kv[0]] * 10 + kv[1]))[:VOCAB_SIZE] if df[t] >= 5]
    X, y, cols = PT.design(rs, vocab, numeric)
    print(f"{len(rs)} pairs, {int(y.sum())} in one value, {len(cols)} features ({len(vocab)} words), "
          f"{len({r['form'] for r in rs})} forms")
    forms = sorted({r["form"] for r in rs})
    fold_of = {f: i % 5 for i, f in enumerate(forms)}
    folds = np.array([fold_of[r["form"]] for r in rs])
    p_all = np.zeros(len(rs))
    for k in range(5):
        tr, te = folds != k, folds == k
        mean, std = X[tr].mean(0), X[tr].std(0) + 1e-9
        w = PT.fit(X[tr], y[tr], mean, std)
        p_all[te] = PT.predict(X[te], w, mean, std)
    best = max((PT.prf(y, p_all, c) + (c,) for c in np.arange(0.2, 0.95, 0.05)), key=lambda t: t[2])
    print(f"folds by form (pairs): best cut {best[3]:.2f}  P {best[0]:.1%}  R {best[1]:.1%}  F1 {best[2]:.1%}")
    mean, std = X.mean(0), X.std(0) + 1e-9
    w = PT.fit(X, y, mean, std)
    weights = {c: round(float(v), 5) for c, v in zip(cols, w[:-1])}
    weights["bias"] = round(float(w[-1]), 5)
    top = sorted(weights.items(), key=lambda kv: -abs(kv[1]))[:25]
    print("strongest:", ", ".join(f"{k} {v:+.2f}" for k, v in top))
    consts = {"VOCAB": tuple(vocab), "MEAN": {c: round(float(v), 5) for c, v in zip(cols, mean)},
              "STD": {c: round(float(v), 5) for c, v in zip(cols, std)}, "WEIGHTS": weights, "CUT": round(float(best[3]), 2)}
    if args.paste:
        p = ROOT / "petey/validate/split_model.py"
        t = p.read_text()
        head = t.split("# ---- the fitted model")[0]
        tail = t[t.index("\n\ndef score("):]
        block = ("# ---- the fitted model (eval/split_train.py pastes these) ----\n"
                 f"VOCAB: tuple = {consts['VOCAB']!r}\nMEAN: dict = {consts['MEAN']!r}\nSTD: dict = {consts['STD']!r}\n"
                 f"WEIGHTS: Optional[dict] = {consts['WEIGHTS']!r}\nCUT = {consts['CUT']}\n")
        p.write_text(head + block + tail)
        print(f"pasted into {p}")
    else:
        (ROOT / "runs/benchmark/split_model.json").write_text(json.dumps(consts, indent=1))
        print("constants -> runs/benchmark/split_model.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
