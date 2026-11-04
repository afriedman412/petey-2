"""The split model: do these two neighbouring text boxes on a line hold one value (a date in month / day / year
boxes, a phone in area / prefix / line, an ID number in pieces)? A logistic regression over the pair and its run,
trained on the tuning set by `eval/split_train.py` (numpy, folds by form, as `same_box` and `printed_model`), its
weights pasted below. Andrew, 2026-11-04: "we are at the limit of what rules can do", train local models.

    features(a, b, run, words, page) -> {name: value}   a, b adjacent in `run` (compound_values._runs), {rect, code}
    score(a, b, run, words, page) -> probability        None until WEIGHTS are set
    chains(run, words, page) -> [[box, ...], ...]      the run's values: maximal stretches of pairs scoring >= CUT

The features: the gap and the boxes' sizes; what is printed between them (nothing, separators, a word); each box's
own caption and whether a caption phrase spans both (the own-caption cut, learned here instead of ruled); the cue
words over the run (the kinds' words and part labels, `compound_values`); the run's length and the pair's place in
it; the common words over the run (`VOCAB`, learned). Page-only.
"""
from __future__ import annotations

import math
import re
from typing import Optional

from petey.validate import compound_values as cv

TOKEN = re.compile(r"[a-z]{2,}")
_PART_WORDS = {tok for parts in cv._PRINTED.values() for tok in parts}


def _real(w) -> bool:
    return cv._real_word(w)


def _own_real(b: dict, words: list, page: list) -> list:
    return [w for w in cv._own_words(b, words, "above", page) if _real(w)]


def _run_caption(run: list[dict], words: list, page: list) -> list:
    x0, y0 = run[0]["rect"][0], min(b["rect"][1] for b in run)
    x1, y1 = run[-1]["rect"][2], max(b["rect"][3] for b in run)
    above = cv._words_over(words, x0, x1, y0 - cv.ABOVE, y0 + 1)
    under = [w for w in cv._words_over(words, x0, x1, y1 - 1, y1 + cv.BELOW)
             if not any(o["rect"][1] >= w[1] and o["rect"][1] - w[3] < w[1] - y1
                        and min(o["rect"][2], w[2]) > max(o["rect"][0], w[0]) for o in page)]
    return above + cv._label_left(words, run[0]["rect"]) + under


def features(a: dict, b: dict, run: list[dict], words: list, page: list) -> dict:
    ax0, ay0, ax1, ay1 = a["rect"]
    bx0, by0, bx1, by1 = b["rect"]
    aw, bw = max(ax1 - ax0, 1.0), max(bx1 - bx0, 1.0)
    ah, bh = max(ay1 - ay0, 1.0), max(by1 - by0, 1.0)
    gap = bx0 - ax1
    between = [w for w in words if ax1 - 2 <= w[0] and w[2] <= bx0 + 2
               and min(ay1, by1) - 2 <= (w[1] + w[3]) / 2 <= max(ay0, by0) + max(ah, bh) + 2]
    btxt = " ".join(w[4] for w in between)
    y0 = min(x["rect"][1] for x in run)
    above = [w for w in words if y0 - cv.ABOVE <= (w[1] + w[3]) / 2 <= y0 + 1
             and run[0]["rect"][0] - 2 <= w[0] <= run[-1]["rect"][2]]
    spans = any(ph[0][0] <= (ax0 + ax1) / 2 and ph[-1][2] >= (bx0 + bx1) / 2 for ph in cv._phrases(above))
    b_start = any(bx0 - 2 <= ph[0][0] <= bx1 - 2 and any(_real(w) for w in ph) for ph in cv._phrases(above))
    cap = cv._text(_run_caption(run, words, page))
    kinds = {k: float(any(re.search(r"(?<![a-z])" + re.escape(c) + r"(?![a-z])", cap) for c in cues))
             for k, cues in cv._KIND_WORDS.items()}
    a_parts = cv._part_words(cv._own_words(a, words, "above", page) + cv._own_words(a, words, "below", page))
    b_parts = cv._part_words(cv._own_words(b, words, "above", page) + cv._own_words(b, words, "below", page))
    i = next((k for k, x in enumerate(run) if x is a or x["code"] == a["code"]), 0)
    n = len(run)
    f = {
        "gap": math.log1p(max(gap, 0.0)), "gap_h": max(gap, 0.0) / max(ah, bh), "touch": float(gap <= 2),
        "log_aw": math.log(aw), "log_bw": math.log(bw), "w_ratio": math.log(aw / bw), "h_ratio": math.log(ah / bh),
        "both_narrow": float(aw <= cv.COMB_WIDTH and bw <= cv.COMB_WIDTH),
        "both_part": float(aw <= cv.PART_WIDTH["date"] and bw <= cv.PART_WIDTH["date"]),
        "a_shorter": float(aw <= 0.8 * bw), "aligned": float(abs(ay0 - by0) <= 2),
        "between_none": float(not between), "between_sep": float(bool(between) and all(set(w[4]) <= cv._SEPARATOR for w in between)),
        "between_word": float(any(_real(w) for w in between)),
        "between_dash": float("-" in btxt or "–" in btxt), "between_slash": float("/" in btxt), "between_paren": float(")" in btxt or "(" in btxt),
        "a_own": float(bool(_own_real(a, words, page))), "b_own": float(bool(_own_real(b, words, page))),
        "b_start": float(b_start), "spans": float(spans),
        "date_pattern": float(bool(cv._DATE_PATTERN.search(cap))),
        "a_part": float(bool(a_parts)), "b_part": float(bool(b_parts)),
        "same_part_kind": float(bool(a_parts and b_parts and a_parts[0][0] == b_parts[0][0])),
        "date_parts": float(any(k == "date" for k, _ in a_parts + b_parts)),
        "name_parts": float(any(k == "name" for k, _ in a_parts + b_parts)),
        "addr_parts": float(any(k == "address" for k, _ in a_parts + b_parts)),
        "log_n": math.log(n), "n2": float(n == 2), "n3": float(n == 3), "n_big": float(n > 9), "first": float(i == 0),
        "last": float(i == n - 2), "cap_len": math.log1p(len(TOKEN.findall(cap))),
    }
    for k, v in kinds.items():
        f[f"kind:{k}"] = v
    for t in set(TOKEN.findall(cap)):
        f[f"w:{t}"] = 1.0
    return f


# ---- the fitted model (eval/split_train.py pastes these) ----
VOCAB: tuple = ('date', 'of', 'yyyy', 'mm', 'dd', 'number', 'if', 'or', 'the', 'name', 'state', 'to', 'city', 'year', 'and', 'code', 'address', 'zip', 'birth', 'day', 'month', 'security', 'social', 'have', 'last', 'in', 'from', 'first', 'not', 'this', 'for', 'phone', 'telephone', 'you', 'middle', 'jr', 'no', 'suffix', 'ssn', 'does', 'other', 'iii', 'business', 'is', 'an', 'signature', 'any', 'applicable', 'signed', 'account', 'spouse', 'identification', 'mobile', 'country', 'town', 'work', 'parent', 'street', 'given', 'beg', 'periods', 'postal', 'family', 'part', 'on', 'amount', 'yes', 'all', 'income', 'enter', 'province', 'your', 'title', 'end', 'employment', 'made', 'individual', 'line', 'occurrence', 'employer', 'total', 'what', 'page', 'information', 'student', 'etc', 'home', 'taxpayer', 'type', 'area', 'patient', 'when', 'mlpf', 'was', 'form', 'by', 'email', 'person', 'see', 'initial')
MEAN: dict = {'a_own': 0.40871, 'a_part': 0.23926, 'a_shorter': 0.17807, 'addr_parts': 0.1669, 'aligned': 0.97313, 'b_own': 0.33261, 'b_part': 0.22514, 'b_start': 0.2422, 'between_dash': 0.0, 'between_none': 0.99843, 'between_paren': 0.0, 'between_sep': 0.0002, 'between_slash': 0.0002, 'between_word': 0.00039, 'both_narrow': 0.00667, 'both_part': 0.31379, 'cap_len': 1.43781, 'date_parts': 0.03628, 'date_pattern': 0.0757, 'first': 0.58894, 'gap': 1.73864, 'gap_h': 0.61738, 'h_ratio': 0.01065, 'kind:date': 0.12473, 'kind:id_number': 0.04158, 'kind:phone': 0.05766, 'kind:time': 0.00451, 'last': 0.60541, 'log_aw': 4.6631, 'log_bw': 4.5537, 'log_n': 1.09725, 'n2': 0.3281, 'n3': 0.35478, 'n_big': 0.0002, 'name_parts': 0.0759, 'same_part_kind': 0.18357, 'spans': 0.03805, 'touch': 0.5103, 'w_ratio': 0.10939, 'w:date': 0.121, 'w:of': 0.15474, 'w:yyyy': 0.07139, 'w:mm': 0.07119, 'w:dd': 0.07001, 'w:number': 0.10767, 'w:if': 0.09041, 'w:or': 0.09002, 'w:the': 0.05648, 'w:name': 0.14042, 'w:state': 0.09531, 'w:to': 0.05687, 'w:city': 0.08158, 'w:year': 0.0204, 'w:and': 0.06315, 'w:code': 0.07864, 'w:address': 0.07178, 'w:zip': 0.07747, 'w:birth': 0.03099, 'w:day': 0.01177, 'w:month': 0.0102, 'w:security': 0.01745, 'w:social': 0.01726, 'w:have': 0.01432, 'w:last': 0.06295, 'w:in': 0.03687, 'w:from': 0.03157, 'w:first': 0.0553, 'w:not': 0.01314, 'w:this': 0.03118, 'w:for': 0.03216, 'w:phone': 0.0253, 'w:telephone': 0.02961, 'w:you': 0.01471, 'w:middle': 0.04923, 'w:jr': 0.01726, 'w:no': 0.0253, 'w:suffix': 0.0151, 'w:ssn': 0.01059, 'w:does': 0.00549, 'w:other': 0.03667, 'w:iii': 0.00667, 'w:business': 0.02079, 'w:is': 0.02098, 'w:an': 0.00922, 'w:signature': 0.03609, 'w:any': 0.02981, 'w:applicable': 0.03275, 'w:signed': 0.00784, 'w:account': 0.01726, 'w:spouse': 0.00843, 'w:identification': 0.0102, 'w:mobile': 0.00824, 'w:country': 0.03059, 'w:town': 0.02844, 'w:work': 0.00667, 'w:parent': 0.00451, 'w:street': 0.02393, 'w:given': 0.02922, 'w:beg': 0.00314, 'w:periods': 0.00314, 'w:postal': 0.02804, 'w:family': 0.02804, 'w:part': 0.01843, 'w:on': 0.02216, 'w:amount': 0.02353, 'w:yes': 0.01059, 'w:all': 0.01255, 'w:income': 0.01647, 'w:enter': 0.01059, 'w:province': 0.02197, 'w:your': 0.01569, 'w:title': 0.0149, 'w:end': 0.0051, 'w:employment': 0.0049, 'w:made': 0.00431, 'w:individual': 0.00549, 'w:line': 0.01863, 'w:occurrence': 0.00255, 'w:employer': 0.00863, 'w:total': 0.01843, 'w:what': 0.00667, 'w:page': 0.01824, 'w:information': 0.01039, 'w:student': 0.00235, 'w:etc': 0.01785, 'w:home': 0.00412, 'w:taxpayer': 0.00216, 'w:type': 0.01667, 'w:area': 0.00294, 'w:patient': 0.00431, 'w:when': 0.00431, 'w:mlpf': 0.00216, 'w:was': 0.00588, 'w:form': 0.01549, 'w:by': 0.01157, 'w:email': 0.01157, 'w:person': 0.01098, 'w:see': 0.01059, 'w:initial': 0.01451}
STD: dict = {'a_own': 0.4916, 'a_part': 0.42663, 'a_shorter': 0.38258, 'addr_parts': 0.37288, 'aligned': 0.1617, 'b_own': 0.47115, 'b_part': 0.41768, 'b_start': 0.42842, 'between_dash': 0.0, 'between_none': 0.03958, 'between_paren': 0.0, 'between_sep': 0.014, 'between_slash': 0.014, 'between_word': 0.0198, 'both_narrow': 0.08138, 'both_part': 0.46403, 'cap_len': 1.07583, 'date_parts': 0.18699, 'date_pattern': 0.26452, 'first': 0.49203, 'gap': 1.03871, 'gap_h': 0.83841, 'h_ratio': 0.0652, 'kind:date': 0.33041, 'kind:id_number': 0.19962, 'kind:phone': 0.2331, 'kind:time': 0.06701, 'last': 0.48876, 'log_aw': 0.67446, 'log_bw': 0.65345, 'log_n': 0.34495, 'n2': 0.46952, 'n3': 0.47845, 'n_big': 0.014, 'name_parts': 0.26483, 'same_part_kind': 0.38713, 'spans': 0.19131, 'touch': 0.49989, 'w_ratio': 0.68579, 'w:date': 0.32613, 'w:of': 0.36165, 'w:yyyy': 0.25747, 'w:mm': 0.25714, 'w:dd': 0.25517, 'w:number': 0.30996, 'w:if': 0.28677, 'w:or': 0.28621, 'w:the': 0.23085, 'w:name': 0.34742, 'w:state': 0.29365, 'w:to': 0.2316, 'w:city': 0.27373, 'w:year': 0.14135, 'w:and': 0.24323, 'w:code': 0.26918, 'w:address': 0.25812, 'w:zip': 0.26733, 'w:birth': 0.17328, 'w:day': 0.10784, 'w:month': 0.10047, 'w:security': 0.13096, 'w:social': 0.13023, 'w:have': 0.11879, 'w:last': 0.24288, 'w:in': 0.18844, 'w:from': 0.17487, 'w:first': 0.22857, 'w:not': 0.11387, 'w:this': 0.17381, 'w:for': 0.17643, 'w:phone': 0.15703, 'w:telephone': 0.16952, 'w:you': 0.12038, 'w:middle': 0.21634, 'w:jr': 0.13023, 'w:no': 0.15703, 'w:suffix': 0.12195, 'w:ssn': 0.10236, 'w:does': 0.0739, 'w:other': 0.18796, 'w:iii': 0.08138, 'w:business': 0.14268, 'w:is': 0.14333, 'w:an': 0.09556, 'w:signature': 0.1865, 'w:any': 0.17006, 'w:applicable': 0.17799, 'w:signed': 0.08822, 'w:account': 0.13023, 'w:spouse': 0.09144, 'w:identification': 0.10047, 'w:mobile': 0.09038, 'w:country': 0.17222, 'w:town': 0.16622, 'w:work': 0.08138, 'w:parent': 0.06701, 'w:street': 0.15282, 'w:given': 0.16843, 'w:beg': 0.05593, 'w:periods': 0.05593, 'w:postal': 0.1651, 'w:family': 0.1651, 'w:part': 0.13452, 'w:on': 0.14721, 'w:amount': 0.15159, 'w:yes': 0.10236, 'w:all': 0.11133, 'w:income': 0.12729, 'w:enter': 0.10236, 'w:province': 0.14657, 'w:your': 0.12427, 'w:title': 0.12117, 'w:end': 0.07123, 'w:employment': 0.06985, 'w:made': 0.06554, 'w:individual': 0.0739, 'w:line': 0.13522, 'w:occurrence': 0.05043, 'w:employer': 0.09249, 'w:total': 0.13452, 'w:what': 0.08138, 'w:page': 0.13381, 'w:information': 0.10142, 'w:student': 0.04845, 'w:etc': 0.13239, 'w:home': 0.06404, 'w:taxpayer': 0.0464, 'w:type': 0.12803, 'w:area': 0.05416, 'w:patient': 0.06554, 'w:when': 0.06554, 'w:mlpf': 0.0464, 'w:was': 0.07648, 'w:form': 0.1235, 'w:by': 0.10694, 'w:email': 0.10694, 'w:person': 0.10422, 'w:see': 0.10236, 'w:initial': 0.11959}
WEIGHTS: Optional[dict] = {'a_own': 0.10313, 'a_part': -0.00717, 'a_shorter': 0.64226, 'addr_parts': -0.17607, 'aligned': 0.34131, 'b_own': -0.2955, 'b_part': 0.02056, 'b_start': -0.32296, 'between_dash': 0.0, 'between_none': -0.06282, 'between_paren': 0.0, 'between_sep': 0.00457, 'between_slash': 0.00457, 'between_word': -0.06304, 'both_narrow': 0.0786, 'both_part': 0.5157, 'cap_len': -0.74446, 'date_parts': 0.25544, 'date_pattern': 0.14043, 'first': -0.0125, 'gap': 0.0035, 'gap_h': -0.35917, 'h_ratio': 0.06192, 'kind:date': 0.28647, 'kind:id_number': 0.16999, 'kind:phone': 0.1395, 'kind:time': -0.00142, 'last': -0.22204, 'log_aw': -1.32814, 'log_bw': -1.07462, 'log_n': -0.0602, 'n2': 0.14432, 'n3': 0.12124, 'n_big': -0.01332, 'name_parts': -0.17383, 'same_part_kind': 0.21466, 'spans': 0.26779, 'touch': -0.73349, 'w_ratio': -0.28226, 'w:date': 0.1216, 'w:of': -0.11661, 'w:yyyy': 0.06222, 'w:mm': 0.06016, 'w:dd': 0.18143, 'w:number': 0.05183, 'w:if': 0.01227, 'w:or': -0.0883, 'w:the': -0.00369, 'w:name': 0.00694, 'w:state': -0.06049, 'w:to': 0.09316, 'w:city': -0.00238, 'w:year': -0.02495, 'w:and': -0.16849, 'w:code': -0.26563, 'w:address': 0.03514, 'w:zip': -0.23801, 'w:birth': 0.13547, 'w:day': -0.01707, 'w:month': 0.19391, 'w:security': 0.02564, 'w:social': 0.03052, 'w:have': 0.18948, 'w:last': -0.21003, 'w:in': 0.06449, 'w:from': 0.09445, 'w:first': 0.12878, 'w:not': 0.02088, 'w:this': 0.18457, 'w:for': -0.16567, 'w:phone': 0.04613, 'w:telephone': 0.05486, 'w:you': 0.03187, 'w:middle': 0.0062, 'w:jr': -0.02683, 'w:no': 0.05709, 'w:suffix': -0.08962, 'w:ssn': -0.13659, 'w:does': -0.09258, 'w:other': -0.10158, 'w:iii': 0.045, 'w:business': 0.18899, 'w:is': -0.16725, 'w:an': -0.05232, 'w:signature': 0.07739, 'w:any': -0.07569, 'w:applicable': 0.10014, 'w:signed': 0.38245, 'w:account': 0.09352, 'w:spouse': 0.00819, 'w:identification': 0.20334, 'w:mobile': 0.39211, 'w:country': -0.0183, 'w:town': -0.02325, 'w:work': 0.18917, 'w:parent': 0.05217, 'w:street': 0.09708, 'w:given': 0.1283, 'w:beg': 0.11311, 'w:periods': 0.11311, 'w:postal': 0.06103, 'w:family': 0.14311, 'w:part': 0.01175, 'w:on': -0.1318, 'w:amount': 0.01692, 'w:yes': -0.01593, 'w:all': 0.2003, 'w:income': -0.05721, 'w:enter': -0.05654, 'w:province': 0.07373, 'w:your': 0.06789, 'w:title': -0.08319, 'w:end': -0.09177, 'w:employment': 0.20722, 'w:made': 0.08614, 'w:individual': 0.02103, 'w:line': -0.14086, 'w:occurrence': 0.12841, 'w:employer': 0.01769, 'w:total': -0.30318, 'w:what': -0.04728, 'w:page': -0.15558, 'w:information': 0.03824, 'w:student': 0.05622, 'w:etc': -0.09202, 'w:home': 0.13074, 'w:taxpayer': -0.00512, 'w:type': -0.00614, 'w:area': 0.30329, 'w:patient': 0.08613, 'w:when': 0.05248, 'w:mlpf': 0.18448, 'w:was': -0.04976, 'w:form': -0.22619, 'w:by': -0.01709, 'w:email': 0.06607, 'w:person': -0.05777, 'w:see': -0.03879, 'w:initial': 0.01261, 'bias': -4.47112}
CUT = 0.85


def score(a: dict, b: dict, run: list[dict], words: list, page: list) -> Optional[float]:
    if WEIGHTS is None:
        return None
    f = features(a, b, run, words, page)
    z = WEIGHTS.get("bias", 0.0)
    for k, wt in WEIGHTS.items():
        if k == "bias":
            continue
        v = f.get(k, 0.0)
        if k in MEAN:
            v = (v - MEAN[k]) / (STD[k] or 1.0)
        z += wt * v
    return 1.0 / (1.0 + math.exp(-z))


def chains(run: list[dict], words: list, page: list) -> list[list[dict]]:
    """The run's values: maximal stretches whose adjacent pairs all score >= CUT (two or more boxes)."""
    out, cur = [], [run[0]]
    for a, b in zip(run, run[1:]):
        if score(a, b, run, words, page) >= CUT:
            cur.append(b)
        else:
            if len(cur) >= 2:
                out.append(cur)
            cur = [b]
    if len(cur) >= 2:
        out.append(cur)
    return out
