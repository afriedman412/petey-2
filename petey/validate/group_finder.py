"""Suggested option groups among the loose boxes (Andrew, 2026-10-25: "does the finder (and the run finder button) also
handle groups?" ... "yeah that'd be good. anything more complicated that doesn't get picked up automatically is
probably worth of a human look anyways").

Only the clear cases (docs: grouping errs ungrouped), read from the printed page; made groups as the Groups tab loads
and by "run finders" (Andrew, 2026-10-25: "let's have the finder groups group automatically, easy to ungroup them"):

    yes / no      two or three loose checkboxes side by side on one line (or stacked one under the other), their
                  captions Yes and No (and N/A): one question's answers
    one of        a run of two or more loose checkboxes, side by side or stacked, under or after a printed "only one",
                  "check one", "select one", "one box" ...

A suggestion is {items, name, why, page}; ungrouping it on the Groups tab records the boxes in
runs/group_review/not_groups/<id>.json, so it is not made again.

    find(bp, blank) -> [suggestion]
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from petey.paths import RUNS

NOT_GROUPS = RUNS / "group_review" / "not_groups"
YES, NO, NA = {"yes", "y"}, {"no", "n"}, {"n/a", "na", "n.a.", "not applicable", "unknown", "don't know"}
# "the applicable box", singular (2026-10-25, Andrew: CMS-855B's Change / Add / Remove went into blocks as three loose
# boxes under "check the applicable box"; measured on the library: +22 suggestions, all one question's answers)
# not "at least one box" (SSA-3288 p2: a list to check any of)
ONE_OF = re.compile(r"\b(only one|check one|select one|mark one|(?<!least )one box|choose one|check only one|select only one|"
                    r"(?:check|mark|select|tick) the (?:applicable|appropriate|correct) box(?!es))\b", re.I)
LINE_TOL, NEAR = 4.0, 140.0               # points: one line; the most between two boxes of one question


def _words(doc, page: int) -> list[tuple]:
    return [(w[0], w[1], w[2], w[3], w[4]) for w in doc[page - 1].get_text("words")]


def _caption(words: list[tuple], r: list[float], boxes: list[list[float]]) -> str:
    """The words printed just right of a box on its line, up to the next box or a wide gap (up to six words); else the
    word just left of it."""
    cy = (r[1] + r[3]) / 2
    right = sorted((w for w in words if abs((w[1] + w[3]) / 2 - cy) <= 5 and w[0] >= r[2] - 1), key=lambda w: w[0])
    stop = min((b[0] for b in boxes if b is not r and abs((b[1] + b[3]) / 2 - cy) <= 5 and b[0] > r[2]), default=1e9)
    out, x = [], r[2]
    for w in right:
        if w[0] >= stop or w[0] - x > 14 or len(out) == 6:
            break
        out.append(w[4])
        x = w[2]
    if out:
        return " ".join(out)
    left = [w for w in words if abs((w[1] + w[3]) / 2 - cy) <= 5 and w[2] <= r[0] + 1 and r[0] - w[2] <= 14]
    return max(left, key=lambda w: w[2])[4] if left else ""


def _norm(t: str) -> str:
    return re.sub(r"[^a-z/.' ]+", "", t.lower()).strip(" .")


def _name(fields: list[str]) -> Optional[str]:
    """The group's name from its boxes' parts (Andrew, 2026-10-26: "block and groups need to consider parts as well";
    petey/naming.parts_for): the words their subjects start with, without the yes / no words, and the number they all
    carry (phone_type_home_ind_2, phone_type_cell_ind_2 -> phone_type_2, not phone 1's phone_type); an option group
    has no suffix. Else the boxes' shared start (smoker_yes_ind, smoker_no_ind -> smoker)."""
    from petey import naming
    ps = [naming.parts_for(f) for f in fields]
    subs = [(x.get("subject") or "").split("_") for x in ps]
    its = {x.get("iteration") for x in ps}
    if all(x.get("subject") for x in ps) and len(its) == 1 and None not in its:
        pre = []
        for words in zip(*subs):
            if len(set(words)) > 1:
                break
            pre.append(words[0])
        while pre and pre[-1] in ("yes", "no", "ind", "y", "n"):
            pre.pop()
        if pre and len("_".join(pre)) >= 3:
            return naming.print_name({"subject": "_".join(pre), "iteration": next(iter(its))})
    toks = [f.split("_") for f in fields]
    pre = []
    for parts in zip(*toks):
        if len(set(parts)) > 1:
            break
        pre.append(parts[0])
    while pre and pre[-1] in ("yes", "no", "ind", "y", "n"):
        pre.pop()
    return "_".join(pre) if len(pre) >= 1 and len("_".join(pre)) >= 3 else None


def dismissed(bid: str) -> list[set]:
    p = NOT_GROUPS / f"{bid}.json"
    try:
        return [set(x) for x in json.loads(p.read_text())]
    except (OSError, ValueError):
        return []


def dismiss(bid: str, items: list[str]) -> dict:
    """"not a group": the boxes recorded, so the suggestion stays away."""
    have = dismissed(bid)
    if set(items) not in have:
        have.append(set(items))
    NOT_GROUPS.mkdir(parents=True, exist_ok=True)
    (NOT_GROUPS / f"{bid}.json").write_text(json.dumps([sorted(x) for x in have], indent=1))
    return {"dismissed": sorted(items)}


def find(bp: dict, blank: Optional[Path], loose: dict[str, dict], bid: Optional[str] = None) -> list[dict]:
    """Suggestions among `loose` ({item id: item}, the Groups tab's loose checkboxes: field, page, rect)."""
    if not loose or not blank or not Path(blank).exists():
        return []
    import pymupdf
    # boxes recorded as not a group, and any of them together (f1065 p2: the six entity types ungrouped came back as
    # each line's three)
    nots = dismissed(bid) if bid else []
    skip = lambda ids: any(set(ids) <= d for d in nots)
    out, used = [], set()
    doc = pymupdf.open(str(blank))
    try:
        by_page: dict[int, list] = {}
        for i, it in loose.items():
            by_page.setdefault(int(it["page"]), []).append((i, it))
        for page, its in sorted(by_page.items()):
            if page < 1 or page > len(doc):
                continue
            words = _words(doc, page)
            rects = [list(it["rect"]) for _, it in its]
            cap = {i: _norm(_caption(words, list(it["rect"]), rects)) for i, it in its}

            def runs(across: bool):
                """Boxes one after another on a line (across) or down a column."""
                key = (lambda x: ((x[1]["rect"][1] + x[1]["rect"][3]) / 2, x[1]["rect"][0])) if across else \
                    (lambda x: ((x[1]["rect"][0] + x[1]["rect"][2]) / 2, x[1]["rect"][1]))
                seq = sorted(its, key=key)
                cur = []
                for x in seq:
                    if cur:
                        a, b = cur[-1][1]["rect"], x[1]["rect"]
                        same = abs(key(cur[-1])[0] - key(x)[0]) <= LINE_TOL
                        gap = (b[0] - a[2]) if across else (b[1] - a[3])
                        if not (same and 0 <= gap <= (NEAR if across else 30)):
                            yield cur
                            cur = []
                    cur.append(x)
                if cur:
                    yield cur
            for across in (True, False):
                for run in runs(across):
                    if len(run) < 2:
                        continue
                    # yes / no: windows of 2-3 boxes whose captions are Yes, No (and N/A)
                    k = 0
                    while k < len(run) - 1:
                        for n in (3, 2):
                            win = run[k:k + n]
                            if len(win) < n:
                                continue
                            cs = [cap[i] for i, _ in win]
                            if any(c in YES for c in cs) and any(c in NO for c in cs) and \
                                    all(c in YES | NO | NA for c in cs) and len(set(cs)) == len(cs):
                                ids = [i for i, _ in win]
                                if not (set(ids) & used) and not skip(ids):
                                    used |= set(ids)
                                    out.append({"items": ids, "page": page, "why": "Yes / No on one question",
                                                "name": _name([loose[i]["field"] for i in ids]),
                                                "captions": [cap[i] for i in ids]})
                                k += n - 1
                                break
                        k += 1
                    # one of: a run under / after a printed "only one" (within 40 pt above, or on the line before);
                    # runs under one printed "only one" are one group (f1065 p2: six entity types on two lines)
                    ids = [i for i, _ in run if i not in used]
                    if len(ids) >= 2 and not skip(ids):
                        r0 = loose[ids[0]]["rect"]
                        near = [w for w in words if r0[1] - 40 <= w[3] <= r0[1] + 2 and w[0] <= r0[2] + 400
                                and w[2] >= r0[0] - 400]
                        line = " ".join(w[4] for w in near)
                        m = ONE_OF.search(line)
                        if m:
                            used |= set(ids)
                            cue = tuple(round(c) for c in near[line[:m.start()].count(" ")][:4])  # the printed words
                            prev = next((x for x in out if x.get("cue") == (page, cue)), None)
                            if prev and not skip(prev["items"] + ids):
                                prev["items"] += ids
                                prev["captions"] += [cap[i] for i in ids]
                                prev["name"] = _name([loose[i]["field"] for i in prev["items"]])
                                continue
                            out.append({"items": ids, "page": page, "why": f'"{m.group(0)}" printed above',
                                        "name": _name([loose[i]["field"] for i in ids]),
                                        "captions": [cap[i] for i in ids], "cue": (page, cue)})
    finally:
        doc.close()
    for x in out:
        x.pop("cue", None)
    return out
