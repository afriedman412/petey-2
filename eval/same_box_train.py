"""Train the "same kind of box" model (petey/validate/same_box.py) from the saved block types: for every block's copy
2+ and every position copy 1 fills, each box in that copy's area is a pair with copy 1's box, the saved one the right
answer. Logistic regression in numpy, checked with five folds by form (each form tested by a model that never saw it),
then fitted on all and printed as the constants to paste into same_box.py. Read-only.

    PYTHONPATH=. venv/bin/python eval/same_box_train.py

2026-10-27: 192 forms, 7,157 positions; the true box ranked first among its copy's candidates for 7,098 (folds).
"""
from __future__ import annotations

import collections
import glob
import json
import math
import statistics as st
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petey.paths import RUNS  # noqa: E402
from petey.validate import block_types as bt  # noqa: E402
from petey.validate import hand_review as h  # noqa: E402
from petey.validate import same_box as sb  # noqa: E402


def pairs(rec_path: str) -> list[dict]:
    bid = Path(rec_path).stem
    rec = json.loads(Path(rec_path).read_text())
    types = [t for t in rec.get("types") or [] if len(t.get("blocks") or []) >= 2]
    if not types:
        return []
    try:
        bp = h._load(h.working_path(bid))
    except Exception:            # noqa: BLE001  a form whose blueprint is gone
        return []
    pw = sb.PageWords(bp)
    if pw.doc is None:
        return []
    at = {b["code"]: b for b in bt._boxes(bp)}
    out = []
    for t in types:
        b1 = t["blocks"][0]
        tpl = [at[c] for c in b1 if c and c in at]
        if len(tpl) < 2:
            continue
        height = max(b["rect"][3] for b in tpl) - min(b["rect"][1] for b in tpl)
        width = max(b["rect"][2] for b in tpl) - min(b["rect"][0] for b in tpl)
        for j, bj in enumerate(t["blocks"][1:], 2):
            own = [at[c] for c in bj if c and c in at]
            if len(own) < 2:
                continue
            pg = own[0]["page"]
            box = [min(b["rect"][0] for b in own) - 40, min(b["rect"][1] for b in own) - 25,
                   max(b["rect"][2] for b in own) + 40, max(b["rect"][3] for b in own) + 25]
            cands = [b for b in at.values() if b["page"] == pg and b["code"] not in b1 and b["rect"][0] < box[2]
                     and b["rect"][2] > box[0] and b["rect"][1] < box[3] and b["rect"][3] > box[1]]
            for k, c1 in enumerate(b1):
                if not c1 or c1 not in at:
                    continue
                a = at[c1]
                d = [(at[bj[q]]["rect"][0] - at[b1[q]]["rect"][0], at[bj[q]]["rect"][1] - at[b1[q]]["rect"][1])
                     for q in range(min(len(b1), len(bj))) if q != k and b1[q] and bj[q] and b1[q] in at and bj[q] in at]
                if not d:
                    continue
                dx, dy = st.median(x for x, _ in d), st.median(y for _, y in d)
                truth = bj[k] if k < len(bj) else None
                for c in cands:
                    out.append({"form": bid, "key": f"{t['id']}-{j}-{k}", "y": int(c["code"] == truth),
                                "f": features(a, c, dx, dy, height, width, pw.caption(a), pw.caption(c))})
    return out


def features(a, b, dx, dy, height, width, cap_a, cap_b) -> list[float]:
    """same_box.score's inputs, unscaled (the kind as a number: the model learns it is needed)."""
    ra, rb = a["rect"], b["rect"]
    rx, ry = rb[0] - ra[0] - dx, rb[1] - ra[1] - dy
    shared = (len(cap_a & cap_b) / len(cap_a | cap_b)) if (cap_a or cap_b) else -1.0
    cap, wa = max(shared, 0.0), ra[2] - ra[0]
    return [float(bt.same_kind(a["kind"], b["kind"])), math.log1p(abs(rx)), math.log1p(abs(ry)),
            min(abs(rx) / max(width, 1), 2), min(abs(ry) / max(height, 1), 2),
            min(abs((rb[2] - rb[0]) - wa) / max(wa, 1), 3), math.log1p(abs((rb[3] - rb[1]) - (ra[3] - ra[1]))), cap,
            float(shared < 0), cap * math.exp(-(abs(rx) + abs(ry)) / 20)]


def fit(X: np.ndarray, Y: np.ndarray, l2: float = 1e-3, steps: int = 600, lr: float = 0.5) -> np.ndarray:
    w = np.zeros(X.shape[1])
    sw = np.where(Y > 0, (len(Y) - Y.sum()) / max(Y.sum(), 1), 1.0)
    sw /= sw.mean()
    for _ in range(steps):
        p = 1 / (1 + np.exp(-X @ w))
        w -= lr * (X.T @ (sw * (p - Y)) / len(Y) + l2 * w)
    return w


def main() -> int:
    rows = [r for p in sorted(glob.glob(str(RUNS / "hand_review" / "grids" / "*.json"))) for r in pairs(p)]
    X = np.array([r["f"] for r in rows])
    Y = np.array([r["y"] for r in rows], float)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Xs = np.hstack([(X - mu) / sd, np.ones((len(X), 1))])
    forms = sorted({r["form"] for r in rows})
    fold = {f: i % 5 for i, f in enumerate(forms)}
    F = np.array([fold[r["form"]] for r in rows])
    P = np.zeros(len(rows))
    for k in range(5):
        P[F == k] = 1 / (1 + np.exp(-Xs[F == k] @ fit(Xs[F != k], Y[F != k])))
    by = collections.defaultdict(list)
    for i, r in enumerate(rows):
        by[(r["form"], r["key"])].append(i)
    real = [ix for ix in by.values() if any(Y[i] for i in ix)]
    first = sum(1 for ix in real if Y[max(ix, key=lambda i: P[i])] == 1)
    print(f"{len(forms)} forms, {len(real)} positions: the true box ranked first for {first} (folds by form)")
    w = fit(Xs, Y)
    r4 = lambda v: tuple(round(float(x), 4) for x in v)  # noqa: E731
    print(f"MU = {r4(mu)}\nSD = {r4(sd)}\nW = {r4(w[:-1])}\nBIAS = {round(float(w[-1]), 4)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
