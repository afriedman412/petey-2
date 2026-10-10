"""Training pairs for `petey.label.text_match`: (text, field, label), from the blueprints and their blanks. No API.

Names: every text field's publisher texts (tooltip, XFA caption / tooltip) and readable widget path, paired with
its own name (1) and with the names of the fields a swap could involve (`witness.Names.rivals`: near, same
section) plus one other field on the form (0). A text several fields carry is skipped (it names none of them),
and so is any field a person flagged or corrected in hand review.

Captions: every option whose caption the XFA declares or a person wrote, or whose option value the page prints at
its box, paired as (caption, what the option means) with 1, and its siblings' captions
and the other lines printed near its box with 0.

Split by form, not by row: every form a person reviewed (any verdict not written in bulk) is held out (it is the
name test), plus one in five of the rest (`_held_out`); a form's library and judge-eval copies fall together.

    PYTHONPATH=. venv/bin/python eval/text_match_data.py            # -> runs/text_match/{train,test}.jsonl
"""
from __future__ import annotations

import collections
import hashlib
import json
import random
import re
import sys
from pathlib import Path

from petey.label import text_match as tm
from petey.paths import BLUEPRINTS, RUNS
from petey.validate import witness as W
from petey.validate.field_chain import _page_lines, candidate_captions

OUT = RUNS / "text_match"
SOURCES = [BLUEPRINTS, RUNS / "judge_eval" / "blueprints"]


def form_key(bp: dict, path: Path) -> str:
    src = Path(str(bp.get("source_pdf") or path.stem)).stem.lower()
    return re.sub(r"(_fillable|_blank|_v\d+|_run\d+|_prev)$", "", src)


def _held_out(key: str) -> bool:
    return int(hashlib.sha1(key.encode()).hexdigest(), 16) % 5 == 0


def hand_wrong() -> tuple[set[str], set[tuple[str, str]]]:
    """Forms a person reviewed (by form key, so every copy counts) and the fields they flagged or corrected."""
    forms, wrong = set(), set()
    for vp in (RUNS / "hand_review").glob("*.json"):
        v = json.loads(vp.read_text())
        bpt = Path(v["blueprint"])
        if not bpt.exists():
            continue
        key = form_key(W._load(bpt), bpt)
        for name, rec in (v.get("verdicts") or {}).items():
            if not (rec.get("note") or "").startswith(("auto:", "bulk")):
                forms.add(key)                      # a person looked at this form (bulk accepts alone do not count)
            if rec.get("verdict") == "flag" or rec.get("edit"):
                wrong.add((key, name))
    return forms, wrong


def blueprints() -> list[Path]:
    out = []
    for d in SOURCES:
        out += [p for p in sorted(d.glob("*.bpt")) if not re.search(r"_(v\d+|run\d+|prev)$", p.stem)]
    return out


def name_pairs(path: Path, bp: dict, words: dict, wrong: set, rng: random.Random) -> list[dict]:
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    texts: dict[str, list[tuple[str, str]]] = {}
    for n, s in fields.items():
        if s.get("widgets"):
            continue
        w = s.get("widget") or {}
        got = [("publisher", t) for t in map(tm.clean_text, words.get(w.get("path") or "", [])) if t]
        pw = tm.path_words(w.get("path"))
        if pw:
            got.append(("path", pw))
        texts[n] = got
    carriers = collections.Counter(t.lower() for ts in texts.values() for _, t in set(ts))
    names = W.Names(fields)
    others = [n for n in texts]
    rows = []
    for n, ts in texts.items():
        if (form_key(bp, path), n) in wrong:
            continue
        rivals = [r for r in names.rivals(n) if not fields[r].get("widgets")]
        rng.shuffle(rivals)
        negs = rivals[:3]
        pool = [o for o in others if o != n and o not in negs]
        if pool:
            negs.append(rng.choice(pool))
        for kind, t in ts:
            if carriers[t.lower()] > 1:
                continue
            rows.append({"kind": f"name_{kind}", "text": t, "field": tm.name_words(n), "label": 1, "name": n})
            for o in negs:
                rows.append({"kind": f"name_{kind}", "text": t, "field": tm.name_words(o), "label": 0, "name": o,
                             "of": n})
    return rows


def caption_groups(path: Path, bp: dict, words: dict, lines: dict) -> list[dict]:
    """One record per option with a trusted caption: its description, the true caption, and the wrong candidates
    (sibling captions, other printed lines near the box)."""
    out = []
    for g, s in (bp.get("fields") or {}).items():
        ws = s.get("widgets") if isinstance(s, dict) else None
        if not isinstance(ws, dict) or len(ws) < 2:
            continue
        declared = ((s.get("x_petey_xfa") or {}).get("choices")) or {}
        tips = {k: tm.clean_text((words.get(w.get("path") or "") or [None])[0]) for k, w in ws.items()}
        shared = collections.Counter(t.lower() for t in tips.values() if t)
        caps = {}
        for k, w in ws.items():
            # the XFA caption or a person's; an option value the cascade took only when the page prints it at the
            # box (i-130 stores `Y` for Female and `HZL` for Hazel: codes, not captions)
            c = declared.get(k) or (w.get("caption") if w.get("x_petey_caption_source") in ("hand", "xfa") else None)
            if not c and w.get("caption") and w.get("x_petey_caption_source") is None and w.get("rect"):
                near = candidate_captions(w["rect"], lines.get(w.get("page"), []))[:4]
                c = w["caption"] if any(_same(t, w["caption"]) for t in near) else None
            if c and tm.clean_text(c):
                caps[k] = tm.clean_text(c)
        if not caps:
            continue
        for k, cap in caps.items():
            w = ws[k]
            tip = tips.get(k) if tips.get(k) and shared[tips[k].lower()] == 1 else None
            if tip is None and _ORDINAL.fullmatch(k.lower()):
                continue                # option '0' of a Yes / No pair: only the box's position tells, not text
            near = candidate_captions(w["rect"], lines.get(w.get("page"), []))[:4] if w.get("rect") else []
            wrong = [c for kk, c in caps.items() if kk != k] + [t for t in near if not _same(t, cap)]
            out.append({"kind": "caption", "option": tm.option_desc(g, k, tip), "caption": cap,
                        "wrong": list(dict.fromkeys(x for x in wrong if not _same(x, cap)))[:6],
                        "group": g, "key": k})
    return out


_ORDINAL = re.compile(r"\d+|[a-z]|on|off|yes|no|y|n|true|false|number|num")


def _same(a: str, b: str) -> bool:
    na, nb = (" ".join(re.findall(r"[a-z0-9]+", x.lower())) for x in (a, b))
    return bool(na) and (na == nb or na in nb or nb in na)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    reviewed, wrong = hand_wrong()
    rng = random.Random(7)
    split_of: dict[str, str] = {}
    paths = blueprints()
    for p in paths:                                   # a form is held out if any of its copies was hand-reviewed
        bp = W._load(p)
        k = form_key(bp, p)
        if k in reviewed or _held_out(k):
            split_of[k] = "test"
        else:
            split_of.setdefault(k, "train")
    files = {s: open(OUT / f"{s}.jsonl", "w") for s in ("train", "test")}
    counts = collections.Counter()
    for i, p in enumerate(paths):
        bp = W._load(p)
        blank = W.resolve_blank(bp)
        if not blank or not blank.exists():
            continue
        try:
            words = W.publisher_words(blank)
            lines = _page_lines(str(blank))
        except Exception as e:                          # a blank PyMuPDF cannot read (faa_337)
            print(f"  skip {p.name}: {e}", file=sys.stderr)
            continue
        k = form_key(bp, p)
        split = split_of[k]
        src = "lib" if p.parent == BLUEPRINTS else "je"
        for r in name_pairs(p, bp, words, wrong, rng) + caption_groups(p, bp, words, lines):
            r.update({"form": k, "copy": f"{src}__{p.stem}"})
            files[split].write(json.dumps(r) + "\n")
            counts[(split, r["kind"], r.get("label", "group"))] += 1
        if i % 50 == 0:
            print(f"  {i}/{len(paths)}", file=sys.stderr, flush=True)
    for f in files.values():
        f.close()
    forms = collections.Counter(split_of.values())
    print(f"forms: {dict(forms)}")
    for key, n in sorted(counts.items(), key=str):
        print(f"  {n:7}  {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
