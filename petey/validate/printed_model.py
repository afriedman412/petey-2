"""The printed model: is this text box a signature or initials line, meant to be hand-written (Andrew, 2026-11-04:
"we are at the limit of what rules can do", "train local models for these tasks")? A logistic regression over the
box's own caption and its surroundings, trained on the tuning set by `eval/printed_train.py` (numpy, folds by form,
the same pattern as `same_box`), its weights pasted below. Read-only on the page: boxes and printed words.

    features(b, words, page) -> {name: value}      b: {rect, code}; page: the page's boxes (for caption ownership)
    score(b, words, page) -> probability             None until WEIGHTS are set
    CUT                                              the probability that marks a box printed

The features: the box's size and place; its own caption (`printed_caption._own`: above, inside, before, under, a
word between rows to the nearer box), as cue flags and as the common words in it (`VOCAB`, learned); the words
beside it within reach (the loose reading); an "X" printed before it; the boxes next to it on the line and their
captions (a date box beside a signature). No publisher metadata.
"""
from __future__ import annotations

import math
import re
from typing import Optional

from petey.validate import compound_values as cv
from petey.validate import printed_caption as pc

TOKEN = re.compile(r"[a-z]{2,}")
DATE_HINT = re.compile(r"\b(mm|dd|yy|yyyy|month|day|year)\b", re.I)
BESIDE = 160.0      # pt: the loose reading's reach along the line
NEAR = 40.0         # pt: a neighbour box within this of the box's edge


def _tokens(ws: list) -> list[str]:
    return [t for w in ws for t in TOKEN.findall(w[4].lower())]


def features(b: dict, words: list, page: list, size: tuple = (612.0, 792.0)) -> dict:
    x0, y0, x1, y1 = b["rect"]
    w, h = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    pw, ph = size
    own = pc._own(b, words, page)
    own_text = cv._text(own)
    above = cv._own_words(b, words, "above", page)
    below = cv._own_words(b, words, "below", page)
    beside = [wd for wd in words if y0 - 3 <= (wd[1] + wd[3]) / 2 <= y1 + 3 and wd[2] <= x0 + 2 and x0 - wd[2] < BESIDE]
    beside_text = cv._text(beside)
    line = [o for o in page if o is not b and o["code"] != b["code"] and cv._same_line(o["rect"], b["rect"])]
    right = [o for o in line if o["rect"][0] >= x1 - 2]
    left = [o for o in line if o["rect"][2] <= x0 + 2]
    nearest_right = min((o["rect"][0] - x1 for o in right), default=999.0)
    nearest_left = min((x0 - o["rect"][2] for o in left), default=999.0)
    right_caps = cv._text([wd for o in right for wd in pc._own(o, words, page)]) if right else ""
    x_mark = any(wd[4].strip().lower() == "x" and x0 - wd[2] < 20 and y0 - 6 <= (wd[1] + wd[3]) / 2 <= y1 + 6
                 for wd in words)
    f = {
        "log_w": math.log(w), "log_h": math.log(h), "aspect": math.log(w / h), "w_share": w / pw,
        "x_share": x0 / pw, "y_share": y0 / ph, "thin": float(h < 16), "tall": float(h > 30), "wide": float(w > 200),
        "own_cue": float(bool(pc.CUE.search(own_text))), "own_not": float(bool(pc.NOT.search(own_text))),
        "own_says": float(pc.says(own_text)), "own_date_hint": float(bool(DATE_HINT.search(own_text))),
        "above_cue": float(bool(pc.CUE.search(cv._text(above)))), "below_cue": float(bool(pc.CUE.search(cv._text(below)))),
        "own_len": math.log1p(len(_tokens(own))), "own_empty": float(not own_text.strip()),
        "beside_cue": float(bool(pc.CUE.search(beside_text))), "beside_not": float(bool(pc.NOT.search(beside_text))),
        "beside_len": math.log1p(len(_tokens(beside))),
        "x_mark": float(x_mark), "n_line": math.log1p(len(line)),
        "right_near": float(nearest_right < NEAR), "left_near": float(nearest_left < NEAR),
        "right_date": float(bool(pc.NOT.search(right_caps) or DATE_HINT.search(right_caps))),
        "right_cue": float(bool(pc.CUE.search(right_caps))),
    }
    for t in set(_tokens(own)):
        f[f"w:{t}"] = 1.0
    return f


# ---- the fitted model (eval/printed_train.py pastes these) ----
VOCAB: tuple = ('signature', 'of', 'name', 'or', 'the', 'if', 'number', 'and', 'date', 'to', 'applicant', 'in', 'address', 'this', 'sign', 'state', 'dd', 'yyyy', 'mm', 'any', 'other', 'for', 'is', 'city', 'last', 'interpreter', 'first', 'authorized', 'preparer', 'your', 'no', 'code', 'year', 'zip', 'yes', 'form', 'on', 'line', 'middle', 'telephone', 'you', 'from', 'country', 'must', 'person', 'not', 'owner', 'email', 'signed', 'here', 'by', 'be', 'notary', 'information', 'all', 'ink', 'birth', 'applicable', 'day', 'total', 'trustee', 'business', 'print', 'amount', 'income', 'phone', 'street', 'officer', 'public', 'account', 'that', 'etc', 'as', 'have', 'tax', 'required', 'official', 'please', 'town', 'part', 'legal', 'do', 'application', 'given', 'title', 'with', 'provide', 'page', 'complete', 'family', 'individual', 'are', 'enter', 'organization', 'property', 'see', 'type', 'schedule', 'paid', 'at', 'spouse', 'only', 'than', 'an', 'instructions', 'month', 'effective', 'parent', 'my', 'petitioner', 'it', 'use', 'jr', 'sr', 'witness', 'company', 'uscis', 'years', 'section', 'province', 'postal', 'contact', 'full', 'copy', 'which', 'plan', 'security', 'true', 'current', 'what', 'location', 'did', 'more', 'social', 'provider', 'relationship', 'guardian', 'describe', 'printed', 'mail', 'initial', 'was', 'identification', 'representative', 'value', 'attorney', 'primary', 'interest', 'return', 'employer')
MEAN: dict = {'above_cue': 0.01845, 'aspect': 2.02052, 'below_cue': 0.0068, 'beside_cue': 0.00795, 'beside_len': 0.56095, 'beside_not': 0.03172, 'left_near': 0.36853, 'log_h': 2.74024, 'log_w': 4.76076, 'n_line': 0.87498, 'own_cue': 0.02398, 'own_date_hint': 0.05328, 'own_empty': 0.26018, 'own_len': 0.97525, 'own_not': 0.06093, 'own_says': 0.01845, 'right_cue': 0.00795, 'right_date': 0.05774, 'right_near': 0.37712, 'tall': 0.03916, 'thin': 0.58466, 'w_share': 0.26921, 'wide': 0.28361, 'x_mark': 0.00285, 'x_share': 0.44975, 'y_share': 0.47431, 'w:signature': 0.02045, 'w:of': 0.11051, 'w:name': 0.087, 'w:or': 0.05604, 'w:the': 0.05711, 'w:if': 0.05396, 'w:number': 0.06336, 'w:and': 0.04699, 'w:date': 0.0529, 'w:to': 0.03772, 'w:applicant': 0.01038, 'w:in': 0.02509, 'w:address': 0.03963, 'w:this': 0.01892, 'w:sign': 0.00225, 'w:state': 0.02768, 'w:dd': 0.03168, 'w:yyyy': 0.03164, 'w:mm': 0.03138, 'w:any': 0.02462, 'w:other': 0.02322, 'w:for': 0.02058, 'w:is': 0.0176, 'w:city': 0.02292, 'w:last': 0.01828, 'w:interpreter': 0.00651, 'w:first': 0.01726, 'w:authorized': 0.00306, 'w:preparer': 0.00702, 'w:your': 0.01237, 'w:no': 0.01892, 'w:code': 0.01952, 'w:year': 0.01267, 'w:zip': 0.01922, 'w:yes': 0.01913, 'w:form': 0.01382, 'w:on': 0.01526, 'w:line': 0.01667, 'w:middle': 0.01072, 'w:telephone': 0.01548, 'w:you': 0.01407, 'w:from': 0.01548, 'w:country': 0.01548, 'w:must': 0.00332, 'w:person': 0.00583, 'w:not': 0.00829, 'w:owner': 0.00378, 'w:email': 0.01123, 'w:signed': 0.00247, 'w:here': 0.0031, 'w:by': 0.00986, 'w:be': 0.00629, 'w:notary': 0.00187, 'w:information': 0.00846, 'w:all': 0.00583, 'w:ink': 0.00068, 'w:birth': 0.01331, 'w:applicable': 0.01072, 'w:day': 0.00536, 'w:total': 0.01267, 'w:trustee': 0.00157, 'w:business': 0.01157, 'w:print': 0.00549, 'w:amount': 0.01208, 'w:income': 0.01208, 'w:phone': 0.01097, 'w:street': 0.01182, 'w:officer': 0.00306, 'w:public': 0.00276, 'w:account': 0.0077, 'w:that': 0.00765, 'w:etc': 0.00672, 'w:as': 0.00838, 'w:have': 0.0071, 'w:tax': 0.01046, 'w:required': 0.00425, 'w:official': 0.00123, 'w:please': 0.0088, 'w:town': 0.00961, 'w:part': 0.00838, 'w:legal': 0.00391, 'w:do': 0.00302, 'w:application': 0.00387, 'w:given': 0.00804, 'w:title': 0.00804, 'w:with': 0.006, 'w:provide': 0.00514, 'w:page': 0.00506, 'w:complete': 0.00583, 'w:family': 0.00838, 'w:individual': 0.00383, 'w:are': 0.00544, 'w:enter': 0.00791, 'w:organization': 0.00791, 'w:property': 0.00536, 'w:see': 0.00689, 'w:type': 0.0077, 'w:schedule': 0.00765, 'w:paid': 0.00412, 'w:at': 0.00753, 'w:spouse': 0.00323, 'w:only': 0.00387, 'w:than': 0.00459, 'w:an': 0.00608, 'w:instructions': 0.00604, 'w:month': 0.00429, 'w:effective': 0.00676, 'w:parent': 0.00162, 'w:my': 0.00332, 'w:petitioner': 0.00162, 'w:it': 0.00332, 'w:use': 0.00408, 'w:jr': 0.0023, 'w:sr': 0.00225, 'w:witness': 0.00115, 'w:company': 0.00523, 'w:uscis': 0.00179, 'w:years': 0.00259, 'w:section': 0.00514, 'w:province': 0.0051, 'w:postal': 0.00595, 'w:contact': 0.00404, 'w:full': 0.00472, 'w:copy': 0.00213, 'w:which': 0.00378, 'w:plan': 0.002, 'w:security': 0.0054, 'w:true': 0.00115, 'w:current': 0.00536, 'w:what': 0.00532, 'w:location': 0.0051, 'w:did': 0.0051, 'w:more': 0.00417, 'w:social': 0.00502, 'w:provider': 0.00247, 'w:relationship': 0.00497, 'w:guardian': 0.00072, 'w:describe': 0.00485, 'w:printed': 0.00145, 'w:mail': 0.00395, 'w:initial': 0.00306, 'w:was': 0.00476, 'w:identification': 0.00472, 'w:representative': 0.00132, 'w:value': 0.00468, 'w:attorney': 0.00119, 'w:primary': 0.00204, 'w:interest': 0.00455, 'w:return': 0.00285, 'w:employer': 0.00446}
STD: dict = {'above_cue': 0.13459, 'aspect': 0.9029, 'below_cue': 0.0822, 'beside_cue': 0.08882, 'beside_len': 0.73884, 'beside_not': 0.17525, 'left_near': 0.48241, 'log_h': 0.35874, 'log_w': 0.85843, 'n_line': 0.65433, 'own_cue': 0.15299, 'own_date_hint': 0.22459, 'own_empty': 0.43873, 'own_len': 0.91239, 'own_not': 0.23921, 'own_says': 0.13459, 'right_cue': 0.08882, 'right_date': 0.23326, 'right_near': 0.48466, 'tall': 0.19398, 'thin': 0.49278, 'w_share': 0.22501, 'wide': 0.45075, 'x_mark': 0.0533, 'x_share': 0.27265, 'y_share': 0.23635, 'w:signature': 0.14154, 'w:of': 0.31353, 'w:name': 0.28183, 'w:or': 0.23, 'w:the': 0.23204, 'w:if': 0.22594, 'w:number': 0.2436, 'w:and': 0.21161, 'w:date': 0.22383, 'w:to': 0.19051, 'w:applicant': 0.10133, 'w:in': 0.15639, 'w:address': 0.19509, 'w:this': 0.13625, 'w:sign': 0.04742, 'w:state': 0.16406, 'w:dd': 0.17514, 'w:yyyy': 0.17503, 'w:mm': 0.17434, 'w:any': 0.15496, 'w:other': 0.15059, 'w:for': 0.14197, 'w:is': 0.13151, 'w:city': 0.14964, 'w:last': 0.13398, 'w:interpreter': 0.08039, 'w:first': 0.13025, 'w:authorized': 0.05525, 'w:preparer': 0.08347, 'w:your': 0.11055, 'w:no': 0.13625, 'w:code': 0.13833, 'w:year': 0.11185, 'w:zip': 0.1373, 'w:yes': 0.137, 'w:form': 0.11674, 'w:on': 0.1226, 'w:line': 0.12802, 'w:middle': 0.10296, 'w:telephone': 0.12344, 'w:you': 0.1178, 'w:from': 0.12344, 'w:country': 0.12344, 'w:must': 0.05749, 'w:person': 0.0761, 'w:not': 0.09068, 'w:owner': 0.0614, 'w:email': 0.10535, 'w:signed': 0.0496, 'w:here': 0.05563, 'w:by': 0.09883, 'w:be': 0.07908, 'w:notary': 0.04321, 'w:information': 0.0916, 'w:all': 0.0761, 'w:ink': 0.02607, 'w:birth': 0.11459, 'w:applicable': 0.10296, 'w:day': 0.073, 'w:total': 0.11185, 'w:trustee': 0.03963, 'w:business': 0.10692, 'w:print': 0.07386, 'w:amount': 0.10922, 'w:income': 0.10922, 'w:phone': 0.10416, 'w:street': 0.10808, 'w:officer': 0.05525, 'w:public': 0.0525, 'w:account': 0.08739, 'w:that': 0.08715, 'w:etc': 0.08169, 'w:as': 0.09114, 'w:have': 0.08397, 'w:tax': 0.10174, 'w:required': 0.06507, 'w:official': 0.03509, 'w:please': 0.0934, 'w:town': 0.09756, 'w:part': 0.09114, 'w:legal': 0.06242, 'w:do': 0.05486, 'w:application': 0.06208, 'w:given': 0.08929, 'w:title': 0.08929, 'w:with': 0.0772, 'w:provide': 0.07154, 'w:page': 0.07095, 'w:complete': 0.0761, 'w:family': 0.09114, 'w:individual': 0.06174, 'w:are': 0.07357, 'w:enter': 0.08858, 'w:organization': 0.08858, 'w:property': 0.073, 'w:see': 0.08271, 'w:type': 0.08739, 'w:schedule': 0.08715, 'w:paid': 0.06409, 'w:at': 0.08643, 'w:spouse': 0.05675, 'w:only': 0.06208, 'w:than': 0.06761, 'w:an': 0.07774, 'w:instructions': 0.07747, 'w:month': 0.06539, 'w:effective': 0.08195, 'w:parent': 0.04016, 'w:my': 0.05749, 'w:petitioner': 0.04016, 'w:it': 0.05749, 'w:use': 0.06376, 'w:jr': 0.04786, 'w:sr': 0.04742, 'w:witness': 0.03386, 'w:company': 0.07213, 'w:uscis': 0.04222, 'w:years': 0.05086, 'w:section': 0.07154, 'w:province': 0.07125, 'w:postal': 0.07692, 'w:contact': 0.06343, 'w:full': 0.06854, 'w:copy': 0.04606, 'w:which': 0.0614, 'w:plan': 0.04466, 'w:security': 0.07329, 'w:true': 0.03386, 'w:current': 0.073, 'w:what': 0.07271, 'w:location': 0.07125, 'w:did': 0.07125, 'w:more': 0.06442, 'w:social': 0.07066, 'w:provider': 0.0496, 'w:relationship': 0.07036, 'w:guardian': 0.02688, 'w:describe': 0.06945, 'w:printed': 0.03799, 'w:mail': 0.06276, 'w:initial': 0.05525, 'w:was': 0.06884, 'w:identification': 0.06854, 'w:representative': 0.03628, 'w:value': 0.06823, 'w:attorney': 0.03448, 'w:primary': 0.04513, 'w:interest': 0.0673, 'w:return': 0.0533, 'w:employer': 0.06667}
WEIGHTS: Optional[dict] = {'above_cue': 0.47017, 'aspect': 0.49486, 'below_cue': 0.30157, 'beside_cue': 0.27511, 'beside_len': -0.37148, 'beside_not': -0.26076, 'left_near': -0.28169, 'log_h': -0.09615, 'log_w': 0.48032, 'n_line': -0.47431, 'own_cue': -0.06625, 'own_date_hint': -0.04106, 'own_empty': 0.22118, 'own_len': -0.25726, 'own_not': -0.11825, 'own_says': 0.27797, 'right_cue': 0.13616, 'right_date': 0.26337, 'right_near': 0.34268, 'tall': 0.14964, 'thin': 0.45132, 'w_share': -0.84089, 'wide': 0.54544, 'x_mark': 0.1688, 'x_share': -0.11421, 'y_share': 0.61208, 'w:signature': 0.20333, 'w:of': 0.07639, 'w:name': -0.43968, 'w:or': -0.1741, 'w:the': 0.22325, 'w:if': 0.27378, 'w:number': -0.19504, 'w:and': -0.09841, 'w:date': -0.16556, 'w:to': -0.07606, 'w:applicant': 0.04936, 'w:in': -0.03682, 'w:address': -0.25331, 'w:this': -0.04854, 'w:sign': 0.05067, 'w:state': -0.09733, 'w:dd': -0.08875, 'w:yyyy': -0.06965, 'w:mm': -0.08806, 'w:any': -0.05543, 'w:other': -0.1173, 'w:for': 0.18869, 'w:is': -0.1189, 'w:city': -0.16556, 'w:last': -0.07507, 'w:interpreter': 0.05905, 'w:first': -0.07101, 'w:authorized': 0.12331, 'w:preparer': 0.03907, 'w:your': -0.05455, 'w:no': -0.02463, 'w:code': -0.03709, 'w:year': -0.00596, 'w:zip': -0.01018, 'w:yes': -0.11733, 'w:form': -0.06256, 'w:on': 0.00193, 'w:line': -0.0353, 'w:middle': -0.03209, 'w:telephone': -0.08189, 'w:you': -0.17614, 'w:from': -0.06651, 'w:country': -0.15964, 'w:must': 0.11437, 'w:person': -0.07287, 'w:not': 0.02886, 'w:owner': -0.04404, 'w:email': -0.14222, 'w:signed': -0.01204, 'w:here': 0.04056, 'w:by': -0.17879, 'w:be': -0.09961, 'w:notary': 0.02346, 'w:information': 0.02933, 'w:all': 0.071, 'w:ink': 0.12697, 'w:birth': 0.02312, 'w:applicable': 0.01239, 'w:day': -0.04279, 'w:total': -0.11417, 'w:trustee': 0.015, 'w:business': -0.04044, 'w:print': 0.08113, 'w:amount': -0.12294, 'w:income': -0.04451, 'w:phone': -0.15199, 'w:street': -0.00803, 'w:officer': 0.084, 'w:public': -0.01953, 'w:account': -0.07374, 'w:that': -0.08408, 'w:etc': -0.07924, 'w:as': -0.14258, 'w:have': -0.10811, 'w:tax': -0.04318, 'w:required': 0.01778, 'w:official': 0.04453, 'w:please': -0.23676, 'w:town': -0.03173, 'w:part': -0.09789, 'w:legal': -0.04162, 'w:do': 0.08407, 'w:application': -0.02259, 'w:given': 0.01422, 'w:title': -0.09564, 'w:with': -0.01642, 'w:provide': 0.0866, 'w:page': -0.08767, 'w:complete': -0.02835, 'w:family': -0.01173, 'w:individual': -0.06237, 'w:are': -0.11702, 'w:enter': -0.06116, 'w:organization': -0.01478, 'w:property': -0.02399, 'w:see': -0.0292, 'w:type': -0.19593, 'w:schedule': -0.0301, 'w:paid': 0.22402, 'w:at': -0.14109, 'w:spouse': -0.02093, 'w:only': 0.16963, 'w:than': 0.06944, 'w:an': -0.1037, 'w:instructions': -0.11225, 'w:month': 0.15832, 'w:effective': 0.08168, 'w:parent': 0.03958, 'w:my': -0.06312, 'w:petitioner': 0.02324, 'w:it': -0.09496, 'w:use': 0.02188, 'w:jr': -0.00848, 'w:sr': 0.00244, 'w:witness': 0.02245, 'w:company': 0.02796, 'w:uscis': -0.05671, 'w:years': 0.00531, 'w:section': -0.08409, 'w:province': -0.05313, 'w:postal': -0.02904, 'w:contact': -0.03127, 'w:full': -0.18784, 'w:copy': 0.15234, 'w:which': 0.08648, 'w:plan': -0.02193, 'w:security': -0.01846, 'w:true': 0.01438, 'w:current': -0.053, 'w:what': -0.08056, 'w:location': -0.05725, 'w:did': -0.04923, 'w:more': -0.05129, 'w:social': -0.03072, 'w:provider': 0.05727, 'w:relationship': -0.10119, 'w:guardian': -0.03599, 'w:describe': -0.07576, 'w:printed': 0.05496, 'w:mail': -0.05487, 'w:initial': -0.07162, 'w:was': -0.04968, 'w:identification': -0.1003, 'w:representative': 0.04318, 'w:value': -0.00941, 'w:attorney': 0.03962, 'w:primary': -0.04916, 'w:interest': -0.06953, 'w:return': -0.01557, 'w:employer': -0.07613, 'bias': -4.10033}
CUT = 0.85


def score(b: dict, words: list, page: list, size: tuple = (612.0, 792.0)) -> Optional[float]:
    if WEIGHTS is None:
        return None
    f = features(b, words, page, size)
    z = WEIGHTS.get("bias", 0.0)
    for k, wt in WEIGHTS.items():
        if k == "bias":
            continue
        v = f.get(k, 0.0)
        if k in MEAN:
            v = (v - MEAN[k]) / (STD[k] or 1.0)
        z += wt * v
    return 1.0 / (1.0 + math.exp(-z))
