"""The type model: is this box a choice box (a checkbox or radio) or a text box? Replaces the finder's shape call
(a square up to 20 pt is a checkbox, three touching squares a comb, else text) for the boxes it keeps (Andrew,
2026-11-04: "I'm wary of just strapping more rules on"; the character cells of NJ-1040's rows, 13-16 pt squares with
a few points between them, came through as checkboxes). A logistic regression over the box, its company in the row
and the column, and the words beside it; trained on the tuning set by `eval/type_train.py` (numpy, folds by form,
as `same_box`, `printed_model` and `split_model`), weights pasted below. Page-only.

    features(b, boxes, words) -> {name: value}     b: {rect, kind}; boxes: the page's boxes with the finder's kinds
    score(b, boxes, words) -> P(choice)             None until WEIGHTS are set
    kind(b, boxes, words) -> "choice" | "text"

The features: size and shape; the finder's own kind; same-size boxes on the row (count, touching, even spacing,
share of the row) and in the column; a word right beside the box on its line, before it, over it (a checkbox row
has a word beside each box, a cell row none); separators or part labels around it (dashes, slashes, MM / DD);
the common words beside it (`VOCAB`, learned).
"""
from __future__ import annotations

import math
import re
import statistics
from typing import Optional

from petey.validate import compound_values as cv

TOKEN = re.compile(r"[a-z]{2,}")
_PART = {tok for parts in cv._PRINTED.values() for tok in parts}
MARK = ("checkbox", "radio", "radiobutton", "choice")


def _same_size(a: dict, b: dict) -> bool:
    ra, rb = a["rect"], b["rect"]
    return abs((ra[2] - ra[0]) - (rb[2] - rb[0])) <= 2 and abs((ra[3] - ra[1]) - (rb[3] - rb[1])) <= 2


def features(b: dict, boxes: list[dict], words: list) -> dict:
    x0, y0, x1, y1 = b["rect"]
    w, h = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    others = [o for o in boxes if o is not b and o["rect"] != b["rect"]]
    row = [o for o in others if abs(o["rect"][1] - y0) <= 2 and _same_size(o, b)]
    col = [o for o in others if abs(o["rect"][0] - x0) <= 2 and _same_size(o, b) and abs(o["rect"][1] - y0) <= 240]
    on_line = [o for o in others if cv._same_line(o["rect"], b["rect"])]
    xs = sorted([x0] + [o["rect"][0] for o in row])
    gaps = [b2 - a2 for a2, b2 in zip(xs, xs[1:])]
    even = float(len(gaps) >= 2 and statistics.pstdev(gaps) <= 1.5)
    touch = sum(1 for o in row if min(abs(o["rect"][0] - x1), abs(x0 - o["rect"][2])) <= 3)
    nearest = min((max(o["rect"][0] - x1, x0 - o["rect"][2]) for o in row), default=999.0)
    mid = (y0 + y1) / 2
    right = [wd for wd in words if abs((wd[1] + wd[3]) / 2 - mid) <= h and 0 <= wd[0] - x1 <= 12]
    left = [wd for wd in words if abs((wd[1] + wd[3]) / 2 - mid) <= h and 0 <= x0 - wd[2] <= 12]
    above = [wd for wd in words if 0 <= y0 - wd[3] <= 12 and wd[0] < x1 and wd[2] > x0]
    below = [wd for wd in words if 0 <= wd[1] - y1 <= 12 and wd[0] < x1 and wd[2] > x0]
    beside = right + left
    sep = [wd for wd in beside if set(wd[4]) <= cv._SEPARATOR]
    word = [wd for wd in beside if TOKEN.search(wd[4].lower())]
    part = [wd for wd in above + below + beside if wd[4].lower().strip("().:/-") in _PART]
    f = {
        "log_w": math.log(w), "log_h": math.log(h), "aspect": math.log(w / h), "square": float(0.75 <= w / h <= 1.33),
        "small": float(w <= 20 and h <= 20), "tiny": float(w <= 9), "finder_mark": float(b.get("kind") in MARK),
        "row_n": math.log1p(len(row)), "row_many": float(len(row) >= 4), "row_touch": math.log1p(touch),
        "row_even": even, "row_near": float(nearest <= 6), "row_share": len(row) / max(len(on_line), 1),
        "col_n": math.log1p(len(col)), "col_many": float(len(col) >= 2),
        "word_right": float(any(TOKEN.search(wd[4].lower()) for wd in right)), "word_left": float(any(TOKEN.search(wd[4].lower()) for wd in left)),
        "word_beside": float(bool(word)), "sep_beside": float(bool(sep)), "part_label": float(bool(part)),
        "word_above": float(bool(above)), "word_below": float(bool(below)),
        "dash_beside": float(any("-" in wd[4] or "–" in wd[4] for wd in beside)), "slash_beside": float(any("/" in wd[4] for wd in beside)),
        "n_line": math.log1p(len(on_line)),
    }
    for t in {t for wd in beside for t in TOKEN.findall(wd[4].lower())}:
        f[f"w:{t}"] = 1.0
    return f


# ---- the fitted model (eval/type_train.py pastes these) ----
VOCAB: tuple = ('yes', 'no', 'date', 'name', 'state', 'other', 'address', 'zip', 'number', 'yyyy', 'mm', 'dd', 'of', 'the', 'to', 'apt', 'city', 'if', 'phone', 'check', 'code', 'middle', 'and', 'or', 'day', 'year', 'add', 'title', 'email', 'flr', 'change', 'last', 'country', 'ste', 'telephone', 'remove', 'amount', 'mail', 'signature', 'in', 'spouse', 'fax', 'male', 'at', 'not', 'you', 'for', 'female', 'birth', 'relationship', 'specify', 'type', 'by', 'unknown', 'is', 'from', 'this', 'county', 'employer', 'time', 'copy', 'company', 'property', 'applicable', 'exact', 'on', 'hq', 'postcode', 'business', 'applicant', 'first', 'total', 'certify', 'off', 'owner', 'town', 'more', 'hospital', 'account', 'month', 'person', 'am', 'ein', 'non', 'national', 'run', 'employee', 'primary', 'suffix', 'here', 'province', 'partner', 'single', 'married', 'id', 'any', 'home', 'initial', 'an', 'given')
MEAN: dict = {'aspect': 1.45816, 'col_many': 0.54204, 'col_n': 1.12854, 'dash_beside': 0.01787, 'finder_mark': 0.3125, 'log_h': 2.55589, 'log_w': 4.01405, 'n_line': 0.84965, 'part_label': 0.1515, 'row_even': 0.06484, 'row_many': 0.02745, 'row_n': 0.33667, 'row_near': 0.0779, 'row_share': 0.27492, 'row_touch': 0.04516, 'sep_beside': 0.0298, 'slash_beside': 0.02076, 'small': 0.32089, 'square': 0.31341, 'tiny': 0.14961, 'word_above': 0.40433, 'word_below': 0.3436, 'word_beside': 0.4598, 'word_left': 0.22766, 'word_right': 0.31992, 'w:yes': 0.07468, 'w:no': 0.06173, 'w:date': 0.01486, 'w:name': 0.01414, 'w:state': 0.0107, 'w:other': 0.01005, 'w:address': 0.00803, 'w:zip': 0.00767, 'w:number': 0.00745, 'w:yyyy': 0.00741, 'w:mm': 0.00694, 'w:dd': 0.00684, 'w:of': 0.00492, 'w:the': 0.00477, 'w:to': 0.00441, 'w:apt': 0.00387, 'w:city': 0.00383, 'w:if': 0.00362, 'w:phone': 0.00358, 'w:check': 0.00344, 'w:code': 0.00325, 'w:middle': 0.00307, 'w:and': 0.003, 'w:or': 0.00293, 'w:day': 0.00271, 'w:year': 0.0026, 'w:add': 0.00257, 'w:title': 0.0025, 'w:email': 0.0025, 'w:flr': 0.0025, 'w:change': 0.00242, 'w:last': 0.00239, 'w:country': 0.00235, 'w:ste': 0.00235, 'w:telephone': 0.00231, 'w:remove': 0.00231, 'w:amount': 0.00221, 'w:mail': 0.00213, 'w:signature': 0.0021, 'w:in': 0.00203, 'w:spouse': 0.00203, 'w:fax': 0.00199, 'w:male': 0.00192, 'w:at': 0.00184, 'w:not': 0.0017, 'w:you': 0.0017, 'w:for': 0.0017, 'w:female': 0.0017, 'w:birth': 0.00166, 'w:relationship': 0.00156, 'w:specify': 0.00145, 'w:type': 0.00141, 'w:by': 0.00141, 'w:unknown': 0.00137, 'w:is': 0.00134, 'w:from': 0.00134, 'w:this': 0.0013, 'w:county': 0.0013, 'w:employer': 0.00127, 'w:time': 0.00123, 'w:copy': 0.00119, 'w:company': 0.00119, 'w:property': 0.00116, 'w:applicable': 0.00116, 'w:exact': 0.00116, 'w:on': 0.00112, 'w:hq': 0.00112, 'w:postcode': 0.00112, 'w:business': 0.00108, 'w:applicant': 0.00108, 'w:first': 0.00105, 'w:total': 0.00105, 'w:certify': 0.00105, 'w:off': 0.00101, 'w:owner': 0.00101, 'w:town': 0.00101, 'w:more': 0.00101, 'w:hospital': 0.00094, 'w:account': 0.00094, 'w:month': 0.00094, 'w:person': 0.0009, 'w:am': 0.0009, 'w:ein': 0.0009, 'w:non': 0.00087, 'w:national': 0.00087, 'w:run': 0.00087, 'w:employee': 0.00083, 'w:primary': 0.00083, 'w:suffix': 0.00083, 'w:here': 0.00083, 'w:province': 0.00083, 'w:partner': 0.00083, 'w:single': 0.00083, 'w:married': 0.00083, 'w:id': 0.0008, 'w:any': 0.0008, 'w:home': 0.0008, 'w:initial': 0.0008, 'w:an': 0.0008, 'w:given': 0.0008}
STD: dict = {'aspect': 1.20256, 'col_many': 0.49823, 'col_n': 0.97608, 'dash_beside': 0.13246, 'finder_mark': 0.46351, 'log_h': 0.41544, 'log_w': 1.42798, 'n_line': 0.63275, 'part_label': 0.35853, 'row_even': 0.24625, 'row_many': 0.16339, 'row_n': 0.50531, 'row_near': 0.26801, 'row_share': 0.40666, 'row_touch': 0.18744, 'sep_beside': 0.17004, 'slash_beside': 0.14258, 'small': 0.46682, 'square': 0.46388, 'tiny': 0.35669, 'word_above': 0.49076, 'word_below': 0.47491, 'word_beside': 0.49838, 'word_left': 0.41932, 'word_right': 0.46644, 'w:yes': 0.26288, 'w:no': 0.24067, 'w:date': 0.12101, 'w:name': 0.11807, 'w:state': 0.10291, 'w:other': 0.09976, 'w:address': 0.08924, 'w:zip': 0.08723, 'w:number': 0.08599, 'w:yyyy': 0.08578, 'w:mm': 0.08304, 'w:dd': 0.08239, 'w:of': 0.06996, 'w:the': 0.06893, 'w:to': 0.06628, 'w:apt': 0.06209, 'w:city': 0.0618, 'w:if': 0.06003, 'w:phone': 0.05973, 'w:check': 0.05851, 'w:code': 0.05696, 'w:middle': 0.05536, 'w:and': 0.05471, 'w:or': 0.05404, 'w:day': 0.05201, 'w:year': 0.05096, 'w:add': 0.05061, 'w:title': 0.04989, 'w:email': 0.04989, 'w:flr': 0.04989, 'w:change': 0.04916, 'w:last': 0.0488, 'w:country': 0.04843, 'w:ste': 0.04843, 'w:telephone': 0.04805, 'w:remove': 0.04805, 'w:amount': 0.04692, 'w:mail': 0.04614, 'w:signature': 0.04575, 'w:in': 0.04496, 'w:spouse': 0.04496, 'w:fax': 0.04455, 'w:male': 0.04374, 'w:at': 0.04291, 'w:not': 0.04119, 'w:you': 0.04119, 'w:for': 0.04119, 'w:female': 0.04119, 'w:birth': 0.04075, 'w:relationship': 0.0394, 'w:specify': 0.03801, 'w:type': 0.03753, 'w:by': 0.03753, 'w:unknown': 0.03705, 'w:is': 0.03656, 'w:from': 0.03656, 'w:this': 0.03606, 'w:county': 0.03606, 'w:employer': 0.03556, 'w:time': 0.03504, 'w:copy': 0.03453, 'w:company': 0.03453, 'w:property': 0.034, 'w:applicable': 0.034, 'w:exact': 0.034, 'w:on': 0.03346, 'w:hq': 0.03346, 'w:postcode': 0.03346, 'w:business': 0.03292, 'w:applicant': 0.03292, 'w:first': 0.03237, 'w:total': 0.03237, 'w:certify': 0.03237, 'w:off': 0.03181, 'w:owner': 0.03181, 'w:town': 0.03181, 'w:more': 0.03181, 'w:hospital': 0.03065, 'w:account': 0.03065, 'w:month': 0.03065, 'w:person': 0.03006, 'w:am': 0.03006, 'w:ein': 0.03006, 'w:non': 0.02945, 'w:national': 0.02945, 'w:run': 0.02945, 'w:employee': 0.02883, 'w:primary': 0.02883, 'w:suffix': 0.02883, 'w:here': 0.02883, 'w:province': 0.02883, 'w:partner': 0.02883, 'w:single': 0.02883, 'w:married': 0.02883, 'w:id': 0.0282, 'w:any': 0.0282, 'w:home': 0.0282, 'w:initial': 0.0282, 'w:an': 0.0282, 'w:given': 0.0282}
WEIGHTS: Optional[dict] = {'aspect': -1.50947, 'col_many': 0.36155, 'col_n': -0.06395, 'dash_beside': -0.10411, 'finder_mark': 0.71822, 'log_h': -0.66058, 'log_w': -1.46337, 'n_line': -0.77984, 'part_label': -0.148, 'row_even': 0.1474, 'row_many': -0.10864, 'row_n': -0.20117, 'row_near': -0.22739, 'row_share': 0.10084, 'row_touch': 0.36654, 'sep_beside': -0.13669, 'slash_beside': -0.11437, 'small': 0.67883, 'square': 0.71802, 'tiny': 0.65788, 'word_above': -0.01505, 'word_below': -0.11782, 'word_beside': 0.27606, 'word_left': -0.20936, 'word_right': 0.46915, 'w:yes': 0.38759, 'w:no': 0.24355, 'w:date': -0.09898, 'w:name': -0.06598, 'w:state': -0.09205, 'w:other': -0.01652, 'w:address': -0.00037, 'w:zip': -0.12908, 'w:number': -0.13615, 'w:yyyy': -0.1458, 'w:mm': 0.01339, 'w:dd': 0.00622, 'w:of': -0.06455, 'w:the': 0.04493, 'w:to': -0.06484, 'w:apt': 0.06024, 'w:city': -0.03056, 'w:if': 0.02422, 'w:phone': -0.06849, 'w:check': 0.05093, 'w:code': -0.03728, 'w:middle': -0.03995, 'w:and': -0.06413, 'w:or': 0.0068, 'w:day': -0.07589, 'w:year': -0.11093, 'w:add': 0.06833, 'w:title': -0.04529, 'w:email': -0.02868, 'w:flr': 0.04315, 'w:change': 0.06524, 'w:last': -0.00844, 'w:country': -0.03573, 'w:ste': 0.07565, 'w:telephone': -0.03726, 'w:remove': 0.09131, 'w:amount': -0.0634, 'w:mail': -0.01639, 'w:signature': -0.01894, 'w:in': -0.00655, 'w:spouse': 0.09741, 'w:fax': -0.0373, 'w:male': 0.06936, 'w:at': 0.04992, 'w:not': 0.01847, 'w:you': 0.0329, 'w:for': 0.02061, 'w:female': 0.06158, 'w:birth': -0.04634, 'w:relationship': -0.01932, 'w:specify': -0.01139, 'w:type': -0.03403, 'w:by': -0.07797, 'w:unknown': 0.04662, 'w:is': -0.0312, 'w:from': -0.07202, 'w:this': -0.05013, 'w:county': -0.08119, 'w:employer': -0.11427, 'w:time': 0.02938, 'w:copy': 0.00145, 'w:company': 0.08, 'w:property': -0.02625, 'w:applicable': -0.01708, 'w:exact': -0.03705, 'w:on': -0.02924, 'w:hq': -0.0835, 'w:postcode': -0.03974, 'w:business': -0.04769, 'w:applicant': 0.05983, 'w:first': 0.01796, 'w:total': -0.06205, 'w:certify': 0.01055, 'w:off': -0.00133, 'w:owner': -0.04504, 'w:town': -0.01351, 'w:more': 0.02432, 'w:hospital': 0.0303, 'w:account': -0.03609, 'w:month': -0.05377, 'w:person': -0.01677, 'w:am': 0.04052, 'w:ein': -0.02933, 'w:non': 0.03985, 'w:national': -0.01284, 'w:run': 0.00842, 'w:employee': 0.01166, 'w:primary': 0.00559, 'w:suffix': -0.01033, 'w:here': -0.00152, 'w:province': -0.02397, 'w:partner': 0.07012, 'w:single': 0.0586, 'w:married': 0.04402, 'w:id': -0.0277, 'w:any': -0.02908, 'w:home': -0.01699, 'w:initial': 0.00243, 'w:an': 0.04516, 'w:given': -0.01516, 'bias': -1.07963}
CUT = 0.65


def score(b: dict, boxes: list[dict], words: list) -> Optional[float]:
    if WEIGHTS is None:
        return None
    f = features(b, boxes, words)
    z = WEIGHTS.get("bias", 0.0)
    for k, wt in WEIGHTS.items():
        if k == "bias":
            continue
        v = f.get(k, 0.0)
        if k in MEAN:
            v = (v - MEAN[k]) / (STD[k] or 1.0)
        z += wt * v
    return 1.0 / (1.0 + math.exp(-z))


def kind(b: dict, boxes: list[dict], words: list) -> str:
    s = score(b, boxes, words)
    if s is None:
        return "choice" if b.get("kind") in MARK else "text"
    return "choice" if s >= CUT else "text"
