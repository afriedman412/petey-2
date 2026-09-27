#!/usr/bin/env python3
"""score.py pred.json sealed.json [--detail] -- 1:1 greedy IoU matching per page."""
import json, sys
from collections import Counter

def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    I = ix * iy
    U = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - I
    return I / U if U > 0 else 0

def center_in(p, g):
    cx, cy = (p[0]+p[2])/2, (p[1]+p[3])/2
    return g[0] <= cx <= g[2] and g[1] <= cy <= g[3]

GT_MAP = {"Text": "text", "CheckBox": "box", "RadioButton": "box", "Signature": "text",
          "ComboBox": "text", "ListBox": "text"}
PR_MAP = {"text": "text", "comb": "text", "signature": "text", "checkbox": "box", "radio": "box"}

def score(pred, gt, detail=False):
    P = pred["fields"]; G = [g for g in gt["widgets"] if g["rect"][2] - g["rect"][0] > 0.5]
    res = {}
    for thr in (0.5, 0.3):
        pairs = sorted(((iou(p["rect"], g["rect"]), i, j) for i, p in enumerate(P) for j, g in enumerate(G)
                        if p["page"] == g["page"]), reverse=True)
        up, ug, m = set(), set(), []
        for v, i, j in pairs:
            if v < thr: break
            if i in up or j in ug: continue
            up.add(i); ug.add(j); m.append((i, j, v))
        res[thr] = (m, up, ug)
    m, up, ug = res[0.5]
    tp = len(m)
    out = dict(n_pred=len(P), n_gt=len(G),
               P50=tp/len(P) if P else 0, R50=tp/len(G) if G else 0,
               P30=len(res[0.3][0])/len(P) if P else 0, R30=len(res[0.3][0])/len(G) if G else 0,
               mIoU=sum(v for *_, v in m)/tp if tp else 0)
    ci = sum(any(p["page"] == g["page"] and center_in(p["rect"], g["rect"]) for p in P) for g in G)
    out["center_in_R"] = ci / len(G) if G else 0
    tc = Counter()
    for i, j, _ in m:
        gtype, ptype = G[j]["type"], P[i]["kind"]
        ok = GT_MAP.get(gtype) == PR_MAP.get(ptype)
        tc["agree" if ok else "disagree"] += 1
        if gtype == "RadioButton" and ptype == "checkbox": tc["radio_as_checkbox"] += 1
        if gtype == "CheckBox" and ptype == "radio": tc["checkbox_as_radio"] += 1
    out["type"] = dict(tc)
    def inter(a, b):
        return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    merged = 0
    for i in set(range(len(P))) - up:
        kids = [j for j in set(range(len(G))) - ug if G[j]["page"] == P[i]["page"]
                and inter(P[i]["rect"], G[j]["rect"]) >= 0.8 * (G[j]["rect"][2]-G[j]["rect"][0])*(G[j]["rect"][3]-G[j]["rect"][1])]
        if len(kids) >= 2: merged += len(kids)
    out["R50_plus_merged"] = (tp + merged) / len(G) if G else 0
    # Many-to-one (region-level) credit, on top of 1:1 matches at 0.5. Each item counted at most once.
    #   merge: one unmatched pred contains >=2 unmatched GT (each >=80% inside it)
    #   split: one unmatched GT contains >=2 unmatched preds (each >=80% inside it) jointly covering >=50% of it
    area = lambda r: max(0, r[2]-r[0]) * max(0, r[3]-r[1])
    uP, uG = set(range(len(P))) - up, set(range(len(G))) - ug
    cg, cp = set(), set()
    for i in sorted(uP):
        kids = [j for j in uG - cg if G[j]["page"] == P[i]["page"] and inter(P[i]["rect"], G[j]["rect"]) >= 0.8 * area(G[j]["rect"])]
        if len(kids) >= 2: cp.add(i); cg.update(kids)
    for j in sorted(uG - cg):
        frags = [i for i in uP - cp if P[i]["page"] == G[j]["page"] and inter(P[i]["rect"], G[j]["rect"]) >= 0.8 * area(P[i]["rect"])]
        if len(frags) >= 2 and sum(inter(P[i]["rect"], G[j]["rect"]) for i in frags) >= 0.5 * area(G[j]["rect"]):
            cg.add(j); cp.update(frags)
    out["R_m2o"] = (tp + len(cg)) / len(G) if G else 0
    out["P_m2o"] = (tp + len(cp)) / len(P) if P else 0
    out["m2o"] = dict(merge_or_split_gt=len(cg), merge_or_split_pred=len(cp))
    if detail:
        out["unmatched_gt"] = [dict(page=G[j]["page"], rect=[round(x, 1) for x in G[j]["rect"]], type=G[j]["type"],
                                    best_iou=round(max([iou(p["rect"], G[j]["rect"]) for p in P if p["page"] == G[j]["page"]] or [0]), 2))
                               for j in range(len(G)) if j not in ug]
        out["unmatched_pred"] = [dict(page=P[i]["page"], rect=P[i]["rect"], kind=P[i]["kind"], src=P[i]["source"],
                                      cap=P[i]["caption"][:40]) for i in range(len(P)) if i not in up]
    return out

if __name__ == "__main__":
    pred, gt = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
    r = score(pred, gt, "--detail" in sys.argv)
    print(json.dumps(r, indent=1))
