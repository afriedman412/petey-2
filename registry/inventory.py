"""
Derive the blueprint-library inventory from the registry.

Joins registry/registry.db against the .bpt files in blueprints/ and emits:
  registry/export/inventory.json      - the joined dataset
  docs/BLUEPRINT INVENTORY <date>.md  - the human-facing document

The registry is the source of truth; both outputs are derived. Rebuild the
registry first with registry/backfill.py if it is stale.

Usage:  python registry/inventory.py
"""
import collections
import datetime
import json
import re
import sqlite3
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

db = sqlite3.connect(ROOT / "registry/registry.db")
db.row_factory = sqlite3.Row

forms = {r["form_id"]: dict(r) for r in db.execute("SELECT * FROM forms")}

# promoted bpt artifact per form
bpt = {}
for r in db.execute("SELECT form_id, path, spec_version, source_pdf FROM artifacts WHERE kind='bpt' AND status='promoted'"):
    bpt[r["form_id"]] = dict(r)
drafts = collections.Counter(r["form_id"] for r in db.execute(
    "SELECT form_id FROM artifacts WHERE kind='bpt' AND status='draft'"))
widgets = {r["form_id"] for r in db.execute("SELECT form_id FROM artifacts WHERE kind='widget_map'")}
refs = collections.Counter()
for r in db.execute("SELECT form_id, COUNT(*) n FROM external_refs WHERE source='extractbench' GROUP BY form_id"):
    refs[r["form_id"]] = r["n"]
evals = collections.defaultdict(list)
for r in db.execute("SELECT form_id, corpus, score, cases FROM eval_runs"):
    evals[r["form_id"]].append(dict(r))
tags = collections.defaultdict(list)
for r in db.execute("SELECT form_id, tag FROM form_tags ORDER BY tag"):
    tags[r["form_id"]].append(r["tag"])
aliases = collections.defaultdict(list)
for r in db.execute("SELECT alias, form_id FROM aliases ORDER BY alias"):
    aliases[r["form_id"]].append(r["alias"])

# field counts + record_type + binding from the .bpt files
def bpt_stats(path):
    p = ROOT / path if not str(path).startswith("/") else Path(path)
    if not p.exists():
        return None
    try:
        d = yaml.safe_load(p.read_text())
    except Exception:
        return None
    f = d.get("fields") or {}
    def count(fields):
        n = 0
        for v in fields.values():
            n += 1
            if isinstance(v, dict) and isinstance(v.get("fields"), dict):
                n += count(v["fields"])
        return n
    return {
        "n_fields": count(f),
        "n_top": len(f),
        "record_type": d.get("record_type"),
        "binding": (d.get("binding") or {}).get("schema") if isinstance(d.get("binding"), dict) else d.get("binding"),
        "provenance": (d.get("source") or {}).get("provenance") if isinstance(d.get("source"), dict) else None,
        "source": d.get("source"),
    }

rows = []
for fid, f in forms.items():
    a = bpt.get(fid)
    st = bpt_stats(a["path"]) if a else None
    rows.append({
        **f,
        "bpt_path": a["path"] if a else None,
        "spec_version": a["spec_version"] if a else None,
        "source_pdf": a["source_pdf"] if a else None,
        "n_drafts": drafts.get(fid, 0),
        "has_widget_map": fid in widgets,
        "eb_refs": refs.get(fid, 0),
        "evals": evals.get(fid, []),
        "tags": tags.get(fid, []),
        "aliases": aliases.get(fid, []),
        **(st or {}),
    })

out = ROOT / "registry/export/inventory.json"
out.write_text(json.dumps({"generated": datetime.date.today().isoformat(), "forms": rows}, indent=1, default=str))
print("wrote", out, len(rows), "forms")

active = [r for r in rows if r["status"] == "active"]
print("active:", len(active), "with bpt:", sum(1 for r in active if r["bpt_path"]))
print("fields total:", sum(r.get("n_fields") or 0 for r in active))
print("no field count:", [r["form_id"] for r in active if not r.get("n_fields")][:10])


# --- render ---------------------------------------------------------------

d = json.load(open(ROOT / "registry/export/inventory.json"))
rows = d["forms"]
gen = d["generated"]

VERT_LABEL = {
    "tax": "Tax", "immigration": "Immigration", "finance": "Finance & SEC filings",
    "healthcare": "Healthcare", "insurance": "Insurance", "government": "Government & politics",
    "benefits": "Benefits & retirement", "procurement": "Defense & procurement",
    "housing": "Housing", "mortgage": "Mortgage", "real_estate": "Real estate",
    "supply_chain": "Supply chain & customs", "us_courts": "Courts",
    "energy_rrc": "Energy (TX Railroad Commission)", "auto_valuation": "Auto valuation",
    "aviation": "Aviation", "consumer": "Consumer", "legal": "Legal",
    "logistics": "Logistics", "workers_comp": "Workers' comp", None: "Unclassified",
}

def label(v):
    return VERT_LABEL.get(v, (v or "unclassified").replace("_", " ").title())

def short(desc, form_id):
    """The naming clause of the description, as a title. Abbreviation-safe."""
    if not desc:
        return form_id
    t = re.sub(r"\s+", " ", desc.strip())
    # cut at the first clause marker that separates the name from the explanation
    for sep in [" is filed ", " is issued ", " is used ", " is the ", " is a ", " is an ",
                " is ", " — ", " reports ", " covering ", " used by ", " filed by "]:
        i = t.find(sep)
        if i > 15:
            t = t[:i]
            break
    t = t.strip(" ,;:—-")
    if len(t) > 100:
        t = t[:100].rsplit(" ", 1)[0] + "…"
    # close an unbalanced paren left by truncation
    if t.count("(") > t.count(")"):
        t = t[:t.rindex("(")].strip(" ,;:—-")
    return t


by_status = collections.defaultdict(list)
for r in rows:
    by_status[r["status"]].append(r)

act = by_status["active"]
verts = collections.defaultdict(list)
for r in act:
    verts[r["vertical"]].append(r)

L = []
w = L.append
w("# Petey blueprint library — inventory")
w("")
w(f"Generated {gen} from `registry/registry.db` — the source of truth for blueprint lifecycle — "
  "cross-referenced against the `.bpt` files in [`blueprints/`](../blueprints/). "
  "See *Regenerating* at the bottom.")
w("")

# ---- summary
tot_fields = sum(r["n_fields"] for r in act)
w("## Summary")
w("")
w(f"- **{len(act)} active blueprints**, {tot_fields:,} extraction fields total "
  f"(median {sorted(r['n_fields'] for r in act)[len(act)//2]} fields; range {min(r['n_fields'] for r in act)}–{max(r['n_fields'] for r in act)})")
w(f"- **{len(by_status['in_progress'])} in progress**, **{len(by_status['planned'])} planned** — {len(rows)} forms tracked in all")
w(f"- {sum(1 for r in act if r['site_published'])} published to the site library; "
  f"{sum(1 for r in act if r['binding'])} carry a canonical `binding`; "
  f"{sum(1 for r in act if r['has_widget_map'])} have a widget map")
w(f"- All at BPT spec **v1.0**; {sum(1 for r in act if r['n_drafts'])} have a v1.1 draft in flight")
w(f"- {len(set(r['issuer'] for r in act if r['issuer']))} distinct issuers; "
  f"{sum(1 for r in act if r['record_type']=='array')} are `array` record types, the rest `single`")
w("")

# vertical table
w("### By vertical")
w("")
w("| Vertical | Active | Fields | In progress | Planned |")
w("|---|---:|---:|---:|---:|")
ip = collections.Counter(r["vertical"] for r in by_status["in_progress"])
pl = collections.Counter(r["vertical"] for r in by_status["planned"])
for v, rs in sorted(verts.items(), key=lambda kv: -len(kv[1])):
    w(f"| {label(v)} | {len(rs)} | {sum(r['n_fields'] for r in rs):,} | {ip.get(v,0) or ''} | {pl.get(v,0) or ''} |")
extra = sorted(set(list(ip) + list(pl)) - set(verts), key=lambda v: v or "")
for v in extra:
    w(f"| {label(v)} | — | — | {ip.get(v,0) or ''} | {pl.get(v,0) or ''} |")
w(f"| **Total** | **{len(act)}** | **{tot_fields:,}** | **{len(by_status['in_progress'])}** | **{len(by_status['planned'])}** |")
w("")

# issuers
w("### By issuer")
w("")
w("Active blueprints only; forms still in progress or planned are listed further down.")
w("")
iss = collections.Counter(r["issuer"] or "(unattributed)" for r in act)
w("| Issuer | Blueprints |")
w("|---|---:|")
for i, n in iss.most_common():
    w(f"| {i} | {n} |")
w("")

# canonical bindings
w("### Canonical bindings")
w("")
w("Per the [canonical-names retrofit](CANONICAL_NAMES_RETROFIT.md), blueprints bind field names to an "
  "external register where one exists.")
w("")
b = collections.Counter(r["binding"] for r in act if r["binding"])
w("| Register | Blueprints |")
w("|---|---:|")
for k, n in b.most_common():
    w(f"| `{k}` | {n} |")
w(f"| _(none)_ | {sum(1 for r in act if not r['binding'])} |")
w("")

# provenance
w("### Provenance")
w("")
p = collections.Counter(r["provenance"] or "(unrecorded)" for r in act)
w("| How the blueprint was produced | Blueprints |")
w("|---|---:|")
prov_note = {
    "canonical-refactor-v1": "refactored onto a canonical register (MeF / XBRL / ACORD / …)",
    "llm-adjudicated": "original N-draft + adjudicator pipeline (retired)",
    "labeler-derived": "built from the manual widget labeler",
}
for k, n in p.most_common():
    note = prov_note.get(k)
    w(f"| `{k}`{' — ' + note if note else ''} | {n} |")
w("")

# eval coverage
w("### Validation coverage")
w("")
ebf = [r for r in act if r["eb_refs"]]
ev = [r for r in act if r["evals"]]
eb_all = [r for r in rows if r["eb_refs"]]
w(f"- **{len(ebf)} active blueprints have ExtractBench cases** attached "
  f"({sum(r['eb_refs'] for r in act)} case refs across them). "
  f"A further {len(eb_all) - len(ebf)} ExtractBench-referenced forms are still in progress or planned — "
  f"{sum(r['eb_refs'] for r in eb_all)} case refs are on the books in total.")
w(f"- **{len(ev)} blueprint{'' if len(ev)==1 else 's'} ha{'s' if len(ev)==1 else 've'} a recorded eval run** — the honest number; scoring coverage is the thin part of the library")
for r in ev:
    for e in r["evals"]:
        w(f"  - `{r['form_id']}` — {e['corpus']}: **{e['score']:.3f}**" + (f" ({e['cases']} cases)" if e["cases"] else ""))
w("")
w("---")
w("")

# ---- full listing
w("## Active blueprints")
w("")
w("`fields` counts nested fields too. `bind` is the canonical register the field names bind to. "
  "`wm` = widget map present. `EB` = ExtractBench case refs. `1.1` = v1.1 draft in flight.")
w("")
for v, rs in sorted(verts.items(), key=lambda kv: -len(kv[1])):
    w(f"### {label(v)} ({len(rs)})")
    w("")
    w("| Form | Description | Issuer | Juris. | Fields | Bind | wm | EB | 1.1 |")
    w("|---|---|---|---|---:|---|:-:|--:|:-:|")
    for r in sorted(rs, key=lambda r: r["form_id"]):
        bp = r["bpt_path"]
        name = f"[`{r['form_id']}`]({'../' + bp if bp else ''})" if bp else f"`{r['form_id']}`"
        w("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            name, short(r["description"], r["form_id"]).replace("|", "/"),
            r["issuer"] or "", (r["jurisdiction"] or "").replace("us-federal", "US fed"),
            r["n_fields"], f"`{r['binding']}`" if r["binding"] else "",
            "•" if r["has_widget_map"] else "", r["eb_refs"] or "",
            "•" if r["n_drafts"] else ""))
    w("")

# ---- pipeline
for st, head, note in [
    ("in_progress", "In progress", "Registered with a v1.1 draft or a source PDF in hand, but no promoted blueprint yet. "
                                   "These carry no description in the registry — they are tracked slots, not written blueprints."),
    ("planned", "Planned", "Tracked as a demand signal; nothing generated yet."),
]:
    rs = by_status[st]
    if not rs:
        continue
    w(f"## {head} ({len(rs)})")
    w("")
    w(note)
    w("")
    w("| Form | Issuer | Vertical | Origin | Drafts | EB |")
    w("|---|---|---|---|--:|--:|")
    for r in sorted(rs, key=lambda r: (label(r["vertical"]), r["form_id"])):
        w("| `{}` | {} | {} | {} | {} | {} |".format(
            r["form_id"], r["issuer"] or "", label(r["vertical"]),
            r["notes"] or "", r["n_drafts"] or "", r["eb_refs"] or ""))
    w("")

w("---")
w("")
w("## Regenerating")
w("")
w("The registry is tool-written; this document and `registry/export/inventory.json` are both derived from it.")
w("")
w("```")
w("python registry/backfill.py     # refresh the registry from blueprints/ + source_pdfs/")
w("python registry/inventory.py    # re-derive inventory.json + this document")
w("```")
w("")
w("`registry/inventory.py` writes a new dated file rather than overwriting this one. "
  "The browsable equivalent is `registry/report.html` (`python registry/render_html.py`).")
w("")

out = ROOT / f"docs/BLUEPRINT INVENTORY {gen}.md"
out.write_text("\n".join(L))
print("wrote", out)
print(len("\n".join(L)), "chars")
