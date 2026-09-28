"""Render the blueprint-library inventory to a browsable page.

Reads registry/export/inventory.json (written by registry/inventory.py) and emits:

  registry/inventory.html           - standalone page, open in any browser
  registry/inventory.artifact.html  - same page as an Artifact body fragment

The registry is authoritative; both files are read-only renders. Where
report.html covers registry *lifecycle* (what exists, what stage it is at), this
page covers library *composition* - field counts, canonical bindings,
provenance, and validation coverage.

  python registry/inventory.py             # refresh inventory.json first
  python registry/render_inventory_html.py
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "registry/export/inventory.json"
OUT_STANDALONE = ROOT / "registry/inventory.html"
OUT_ARTIFACT = ROOT / "registry/inventory.artifact.html"

VERT_LABEL = {
    "tax": "Tax",
    "immigration": "Immigration",
    "finance": "Finance & SEC",
    "healthcare": "Healthcare",
    "insurance": "Insurance",
    "government": "Government & politics",
    "benefits": "Benefits & retirement",
    "procurement": "Defense & procurement",
    "housing": "Housing",
    "mortgage": "Mortgage",
    "real_estate": "Real estate",
    "supply_chain": "Supply chain & customs",
    "us_courts": "Courts",
    "energy_rrc": "Energy (TX RRC)",
    "auto_valuation": "Auto valuation",
    "aviation": "Aviation",
    "consumer": "Consumer",
    "legal": "Legal",
    "logistics": "Logistics",
    "workers_comp": "Workers' comp",
}

BIND_LABEL = {
    "irs_mef": "IRS MeF",
    "us_gaap_xbrl": "US-GAAP XBRL",
    "acord": "ACORD",
    "sec_edgar": "SEC EDGAR",
    "cbp_ace": "CBP ACE",
    "fincen_bsa": "FinCEN BSA",
    "mismo_v3_4": "MISMO v3.4",
    "fhir_r5": "FHIR R5",
    "fec_fecml": "FEC FECML",
    "x12_837d": "X12 837D",
    "x12_837i": "X12 837I",
    "un_cefact_cii": "UN/CEFACT CII",
    "sec_iard": "SEC IARD",
    "hud_hip": "HUD HIP",
    "senate_lda": "Senate LDA",
    "ulad": "ULAD",
}

PROV_LABEL = {
    "canonical-refactor-v1": "Canonical refactor",
    "llm-adjudicated": "LLM-adjudicated",
    "labeler-derived": "Labeler-derived",
}


def label(v: str | None) -> str:
    return VERT_LABEL.get(v, (v or "unclassified").replace("_", " ").title())


def short(desc: str | None, form_id: str) -> str:
    """The naming clause of a description, as a title. Abbreviation-safe."""
    if not desc:
        return ""
    t = re.sub(r"\s+", " ", desc.strip())
    for sep in (" is filed ", " is issued ", " is used ", " is the ", " is a ",
                " is an ", " is ", " — ", " reports ", " covering ",
                " used by ", " filed by "):
        i = t.find(sep)
        if i > 15:
            t = t[:i]
            break
    t = t.strip(" ,;:—-")
    if len(t) > 120:
        t = t[:120].rsplit(" ", 1)[0] + "…"
    if t.count("(") > t.count(")"):
        t = t[:t.rindex("(")].strip(" ,;:—-")
    return t


def collect() -> dict:
    raw = json.loads(SRC.read_text())
    rows = raw["forms"]

    forms = []
    for r in rows:
        forms.append({
            "id": r["form_id"],
            "st": r["status"],
            "v": label(r["vertical"]),
            "iss": r["issuer"] or "",
            "j": r["jurisdiction"] or "",
            "n": r.get("n_fields") or 0,
            "b": r.get("binding") or "",
            "bl": BIND_LABEL.get(r.get("binding") or "", r.get("binding") or ""),
            "p": PROV_LABEL.get(r.get("provenance") or "", ""),
            "wm": 1 if r["has_widget_map"] else 0,
            "eb": r["eb_refs"] or 0,
            "d11": r["n_drafts"] or 0,
            "site": r["site_published"] or 0,
            "path": r["bpt_path"] or "",
            "t": short(r["description"], r["form_id"]),
            "tags": [t.split(":", 1)[-1] for t in r["tags"]],
            "al": r["aliases"],
            "note": r["notes"] or "",
            "ev": [{"c": e["corpus"], "s": e["score"], "n": e["cases"]}
                   for e in r["evals"]],
        })

    act = [f for f in forms if f["st"] == "active"]
    fields = sorted(f["n"] for f in act)

    verts = Counter(f["v"] for f in act)
    vert_fields = Counter()
    for f in act:
        vert_fields[f["v"]] += f["n"]
    pipeline = Counter(f["v"] for f in forms if f["st"] != "active")

    stats = {
        "active": len(act),
        "in_progress": sum(1 for f in forms if f["st"] == "in_progress"),
        "planned": sum(1 for f in forms if f["st"] == "planned"),
        "fields": sum(fields),
        "median": fields[len(fields) // 2],
        "fmin": fields[0],
        "fmax": fields[-1],
        "bound": sum(1 for f in act if f["b"]),
        "wmap": sum(1 for f in act if f["wm"]),
        "site": sum(1 for f in act if f["site"]),
        "d11": sum(1 for f in act if f["d11"]),
        "eb_active": sum(1 for f in act if f["eb"]),
        "eb_refs_active": sum(f["eb"] for f in act),
        "eb_refs_all": sum(f["eb"] for f in forms),
        "eb_pipeline": sum(1 for f in forms if f["st"] != "active" and f["eb"]),
        "evaluated": sum(1 for f in act if f["ev"]),
        "issuers": len({f["iss"] for f in act if f["iss"]}),
    }

    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "forms": forms,
        "stats": stats,
        "verts": [{"k": k, "n": n, "f": vert_fields[k], "p": pipeline.get(k, 0)}
                  for k, n in verts.most_common()],
        "pipeline_only": [{"k": k, "n": n} for k, n in pipeline.most_common()
                          if k not in verts],
        "issuers": [{"k": k, "n": n} for k, n in
                    Counter(f["iss"] or "(unattributed)" for f in act).most_common()],
        "bindings": [{"k": BIND_LABEL.get(k, k), "n": n} for k, n in
                     Counter(f["b"] for f in act if f["b"]).most_common()],
        "provenance": [{"k": k, "n": n} for k, n in
                       Counter(f["p"] for f in act if f["p"]).most_common()],
        "evals": [{"id": f["id"], "ev": f["ev"]} for f in act if f["ev"]],
    }


PAGE = """<title>Blueprint Library Inventory</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600&display=swap">
<style>
:root {
  color-scheme: light;
  --bg:#eef1f4; --panel:#ffffff; --panel-2:#f7f9fb; --sunk:#e7ecf1;
  --ink:#14202c; --ink-2:#566878; --ink-3:#8899a7;
  --line:#d8e0e7; --line-2:#c3cfd9;
  --accent:#10537f; --accent-soft:#dce9f3;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a;
  --ok-ink:#14724c; --ok-bg:#dcefe5;
  --wip-ink:#8a5a0c; --wip-bg:#fbeed2;
  --plan-ink:#3c5a86; --plan-bg:#e2e9f4;
  --serif:"IBM Plex Serif",Georgia,"Times New Roman",serif;
  --sans:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg:#12171c; --panel:#1a2127; --panel-2:#202931; --sunk:#151b21;
    --ink:#e7edf2; --ink-2:#9aabb8; --ink-3:#6f818e;
    --line:#2c363f; --line-2:#3a4650;
    --accent:#6fb2e0; --accent-soft:#1c2c38;
    --s1:#3987e5; --s2:#d95926; --s3:#199e70;
    --ok-ink:#4fb98c; --ok-bg:#143229;
    --wip-ink:#d49a3a; --wip-bg:#33260f;
    --plan-ink:#7d9fd0; --plan-bg:#1c2738;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg:#12171c; --panel:#1a2127; --panel-2:#202931; --sunk:#151b21;
  --ink:#e7edf2; --ink-2:#9aabb8; --ink-3:#6f818e;
  --line:#2c363f; --line-2:#3a4650;
  --accent:#6fb2e0; --accent-soft:#1c2c38;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70;
  --ok-ink:#4fb98c; --ok-bg:#143229;
  --wip-ink:#d49a3a; --wip-bg:#33260f;
  --plan-ink:#7d9fd0; --plan-bg:#1c2738;
}

*, *::before, *::after { box-sizing:border-box }
body {
  margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.55 var(--sans); -webkit-font-smoothing:antialiased;
}
.wrap { max-width:1160px; margin:0 auto; padding:0 20px; padding-block:40px 64px }
a { color:var(--accent) }

/* ---- masthead ---- */
.mast { border-bottom:2px solid var(--ink); padding-bottom:14px; margin-bottom:8px }
h1 {
  margin:0; font:600 31px/1.15 var(--serif); letter-spacing:-.01em;
  text-wrap:balance;
}
.mast .meta {
  display:flex; flex-wrap:wrap; gap:6px 16px; margin-top:8px;
  font:500 11px/1.4 var(--mono); letter-spacing:.06em; text-transform:uppercase;
  color:var(--ink-3);
}
.lede { color:var(--ink-2); max-width:66ch; margin:18px 0 32px; font-size:15.5px }
.lede strong { color:var(--ink); font-weight:600 }

/* ---- section furniture ---- */
section { margin-bottom:38px }
h2 {
  margin:0 0 3px; font:600 12px/1.3 var(--mono); letter-spacing:.11em;
  text-transform:uppercase; color:var(--ink-2);
}
h2 + .hint { margin:0 0 16px; color:var(--ink-3); font-size:13px; max-width:70ch }
h3 { margin:0 0 12px; font:600 15px/1.3 var(--serif) }

/* ---- stat row: the four numbers the page exists to report ---- */
.stats { display:grid; grid-template-columns:repeat(4,1fr); gap:1px;
  background:var(--line); border:1px solid var(--line); border-radius:4px;
  overflow:hidden; margin-bottom:38px }
.stat { background:var(--panel); padding:16px 18px 15px }
.stat b { display:block; font:500 30px/1 var(--mono); letter-spacing:-.02em;
  font-variant-numeric:tabular-nums }
.stat span { display:block; margin-top:7px; color:var(--ink-2); font-size:12.5px }
.stat.flag b { color:var(--s2) }

/* ---- panels ---- */
.panel { background:var(--panel); border:1px solid var(--line); border-radius:4px;
  padding:18px 20px 20px }
.cols { display:grid; grid-template-columns:1.35fr 1fr; gap:18px; align-items:start }
.stack { display:flex; flex-direction:column; gap:18px }

/* ---- horizontal bar rows ---- */
.bars { display:flex; flex-direction:column; gap:7px }
.bar { display:grid; grid-template-columns:168px 1fr auto; gap:12px;
  align-items:center; cursor:default }
.bar .k { font-size:13px; color:var(--ink-2); text-align:right;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap }
.bar .track { background:var(--sunk); border-radius:2px; height:17px;
  position:relative; overflow:hidden }
.bar .fill { position:absolute; inset:0 auto 0 0; background:var(--s1);
  border-radius:0 4px 4px 0; min-width:2px }
.bar .fill.pipe { background:var(--line-2); border-radius:0 }
.bar .n { font:500 12.5px var(--mono); font-variant-numeric:tabular-nums;
  color:var(--ink); min-width:34px; text-align:right }
.bar:hover .track { outline:1px solid var(--line-2); outline-offset:1px }
.bars.tight { gap:5px }
.bars.tight .bar { grid-template-columns:104px 1fr auto }
.bars.tight .track { height:13px }
.bars.tight .k { font-size:12.5px }

/* ---- histogram ---- */
.hist { display:flex; align-items:flex-end; gap:5px; height:132px; margin-top:4px }
.hcol { flex:1; display:flex; flex-direction:column; justify-content:flex-end;
  gap:5px; height:100% }
.hcol .hb { background:var(--s1); border-radius:4px 4px 0 0; min-height:2px }
.hcol .hn { font:500 11px var(--mono); color:var(--ink-2); text-align:center;
  font-variant-numeric:tabular-nums }
.hax { display:flex; gap:5px; margin-top:7px }
.hax span { flex:1; text-align:center; font:11px var(--mono); color:var(--ink-3) }

/* ---- segmented bar + legend ---- */
.seg { display:flex; gap:2px; height:22px; margin:2px 0 14px }
.seg i { display:block; border-radius:2px }
.legend { display:flex; flex-direction:column; gap:8px }
.lg { display:grid; grid-template-columns:11px 1fr auto; gap:10px; align-items:center;
  font-size:13px }
.lg i { width:11px; height:11px; border-radius:2px }
.lg .lk { color:var(--ink-2) }
.lg .ln { font:500 12.5px var(--mono); font-variant-numeric:tabular-nums }

/* ---- two-column key/value list ---- */
.kv { display:grid; grid-template-columns:1fr auto; gap:6px 14px; font-size:13px }
.kv dt { color:var(--ink-2); overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap }
.kv dd { margin:0; font:500 12.5px var(--mono); font-variant-numeric:tabular-nums }

/* ---- the validation callout: the page's one piece of bad news ---- */
.callout { border:1px solid var(--line); border-left:3px solid var(--s2);
  background:var(--panel); border-radius:0 4px 4px 0; padding:16px 20px }
.callout p { margin:0 0 9px; max-width:72ch; font-size:14px; color:var(--ink-2) }
.callout p:last-child { margin-bottom:0 }
.callout strong { color:var(--ink) }
.evrow { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px }
.ev { background:var(--panel-2); border:1px solid var(--line); border-radius:3px;
  padding:7px 11px; font:12px var(--mono) }
.ev b { font-weight:500; color:var(--ink) }

/* ---- filters ---- */
.filters { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px }
.filters input, .filters select {
  font:14px var(--sans); color:var(--ink); background:var(--panel);
  border:1px solid var(--line-2); border-radius:3px; padding:7px 9px;
}
.filters input { flex:1 1 220px; min-width:0; font-family:var(--mono); font-size:13px }
.filters input:focus-visible, .filters select:focus-visible,
th:focus-visible { outline:2px solid var(--accent); outline-offset:1px }
.tally { margin-left:auto; align-self:center; font:12px var(--mono);
  color:var(--ink-3); white-space:nowrap }

/* ---- table ---- */
.tw { background:var(--panel); border:1px solid var(--line); border-radius:4px;
  overflow-x:auto }
table { border-collapse:collapse; width:100%; font-size:13.5px }
thead th {
  position:sticky; top:0; z-index:1; background:var(--panel-2);
  text-align:left; padding:9px 12px; white-space:nowrap; cursor:pointer;
  font:600 11px var(--mono); letter-spacing:.06em; text-transform:uppercase;
  color:var(--ink-2); border-bottom:1px solid var(--line-2);
}
thead th:hover { color:var(--ink) }
thead th .ar { color:var(--accent) }
td { padding:8px 12px; border-bottom:1px solid var(--line); vertical-align:top }
tbody tr:last-child td { border-bottom:none }
tbody tr:hover { background:var(--panel-2) }
td.id { font:500 12.5px var(--mono); white-space:nowrap }
td.id a { text-decoration:none; border-bottom:1px solid var(--accent-soft) }
td.id a:hover { border-bottom-color:var(--accent) }
td.t { color:var(--ink-2); min-width:260px }
td.num { text-align:right; font:500 12.5px var(--mono);
  font-variant-numeric:tabular-nums; white-space:nowrap }
.chip { display:inline-block; padding:1px 7px; border-radius:9px;
  font:500 11px var(--mono); white-space:nowrap }
.chip.active { background:var(--ok-bg); color:var(--ok-ink) }
.chip.in_progress { background:var(--wip-bg); color:var(--wip-ink) }
.chip.planned { background:var(--plan-bg); color:var(--plan-ink) }
.chip.bind { background:var(--accent-soft); color:var(--accent) }
.flags { display:flex; gap:4px; font:500 10.5px var(--mono); color:var(--ink-3) }
.flags b { font-weight:500; color:var(--accent) }
.empty { padding:28px 14px; text-align:center; color:var(--ink-3); font-size:14px }

footer { margin-top:34px; padding-top:16px; border-top:1px solid var(--line);
  color:var(--ink-3); font-size:12.5px }
footer code { font:12px var(--mono); color:var(--ink-2) }

#tip { position:fixed; z-index:20; pointer-events:none; opacity:0;
  transition:opacity .1s; background:var(--ink); color:var(--bg);
  border-radius:3px; padding:6px 9px; font:12px var(--mono); max-width:250px }

@media (max-width:820px) {
  .stats { grid-template-columns:repeat(2,1fr) }
  .cols { grid-template-columns:1fr }
  .bar { grid-template-columns:120px 1fr auto }
}
@media (max-width:480px) {
  h1 { font-size:25px }
  .bar { grid-template-columns:96px 1fr auto }
  .bar .k { font-size:12px }
}
@media (prefers-reduced-motion:reduce) { * { transition:none !important } }
</style>

<div class="wrap">

<header class="mast">
  <h1>Blueprint Library Inventory</h1>
  <div class="meta">
    <span>generated __GENERATED__</span>
    <span>source: registry.db</span>
    <span>bpt spec v1.0</span>
  </div>
</header>

<p class="lede" id="lede"></p>

<div class="stats" id="stats"></div>

<section>
  <h2>Composition</h2>
  <p class="hint">Blueprints per vertical, with the field count each vertical
    accounts for. The pale extension on a bar is the pipeline &mdash; forms
    registered but not yet promoted.</p>
  <div class="cols">
    <div class="panel">
      <h3>By vertical</h3>
      <div class="bars" id="verts"></div>
    </div>
    <div class="stack">
      <div class="panel">
        <h3>Fields per blueprint</h3>
        <div class="hist" id="hist"></div>
        <div class="hax" id="haxis"></div>
        <p class="hint" style="margin-top:12px" id="histnote"></p>
      </div>
      <div class="panel">
        <h3>By issuer</h3>
        <div class="bars tight" id="issuers"></div>
      </div>
    </div>
  </div>
</section>

<section>
  <h2>Names and origins</h2>
  <p class="hint">Where a blueprint's field names come from, and how the
    blueprint itself was produced.</p>
  <div class="cols">
    <div class="panel">
      <h3>Canonical bindings</h3>
      <dl class="kv" id="bindings"></dl>
    </div>
    <div class="panel">
      <h3>Provenance</h3>
      <div class="seg" id="provseg"></div>
      <div class="legend" id="provleg"></div>
    </div>
  </div>
</section>

<section>
  <h2>Validation coverage</h2>
  <div class="callout" id="callout"></div>
</section>

<section>
  <h2>All forms</h2>
  <p class="hint">Every form the registry tracks, at any stage. Click a column
    heading to sort.</p>
  <div class="filters">
    <input id="q" type="search" placeholder="filter by id, issuer, tag, description&hellip;"
      aria-label="Filter forms">
    <select id="fst" aria-label="Filter by status"><option value="">status: any</option></select>
    <select id="fv" aria-label="Filter by vertical"><option value="">vertical: any</option></select>
    <select id="fb" aria-label="Filter by binding"><option value="">binding: any</option></select>
    <select id="ff" aria-label="Filter by flag">
      <option value="">flag: any</option>
      <option value="bound">canonically bound</option>
      <option value="unbound">no binding</option>
      <option value="wm">has widget map</option>
      <option value="d11">v1.1 draft in flight</option>
      <option value="eb">has ExtractBench cases</option>
      <option value="ev">has an eval run</option>
    </select>
    <span class="tally" id="tally"></span>
  </div>
  <div class="tw">
    <table>
      <thead><tr>
        <th data-k="id">form</th>
        <th data-k="t">description</th>
        <th data-k="iss">issuer</th>
        <th data-k="v">vertical</th>
        <th data-k="n" class="num">fields</th>
        <th data-k="bl">binding</th>
        <th data-k="st">status</th>
        <th data-k="eb" class="num">flags</th>
      </tr></thead>
      <tbody id="tb"></tbody>
    </table>
  </div>
</section>

<footer>
  SQLite is authoritative (<code>registry/registry.db</code>); this page is a
  read-only render. Regenerate with <code>python registry/inventory.py</code>
  then <code>python registry/render_inventory_html.py</code>.
  <code>registry/report.html</code> is the lifecycle view of the same data.
</footer>

</div>
<div id="tip" role="status"></div>

<script>
"use strict";
const DATA = __DATA__;
const LINKS = __LINKS__;
const S = DATA.stats;
const esc = s => String(s ?? "").replace(/[&<>"]/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = n => n.toLocaleString("en-US");
const el = id => document.getElementById(id);

/* ---- lede ---- */
el("lede").innerHTML =
  `Petey's blueprint library holds <strong>${fmt(S.active)} active blueprints</strong> ` +
  `covering ${fmt(S.fields)} extraction fields across ${DATA.verts.length} verticals ` +
  `and ${S.issuers} issuers. Another ${S.in_progress} are in progress and ` +
  `${S.planned} are planned. Every active blueprint is at BPT spec v1.0; ` +
  `${S.d11} have a v1.1 draft in flight.`;

/* ---- stat row ---- */
const TILES = [
  [fmt(S.active), "active blueprints", ""],
  [fmt(S.fields), "extraction fields defined", ""],
  [fmt(S.bound), "bound to a canonical register", ""],
  [fmt(S.evaluated), "with a recorded eval run", "flag"],
];
el("stats").innerHTML = TILES.map(([v, l, c]) =>
  `<div class="stat ${c}"><b>${v}</b><span>${esc(l)}</span></div>`).join("");

/* ---- tooltip ---- */
const tip = el("tip");
function bindTip(node, text) {
  node.addEventListener("pointerenter", e => {
    tip.textContent = text;
    tip.style.opacity = "1";
    move(e);
  });
  node.addEventListener("pointermove", move);
  node.addEventListener("pointerleave", () => { tip.style.opacity = "0"; });
  function move(e) {
    const r = tip.getBoundingClientRect();
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 12;
    if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 12;
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = Math.max(8, y) + "px";
  }
}

/* ---- verticals: one bar per vertical, active + pipeline ---- */
const vmax = Math.max(...DATA.verts.map(v => v.n + v.p), 1);
el("verts").innerHTML = DATA.verts.map(v => `
  <div class="bar" data-tip="${esc(v.k)}: ${v.n} active, ${fmt(v.f)} fields${
    v.p ? ", " + v.p + " in pipeline" : ""}">
    <span class="k" title="${esc(v.k)}">${esc(v.k)}</span>
    <span class="track">
      <span class="fill pipe" style="width:${((v.n + v.p) / vmax * 100).toFixed(2)}%"></span>
      <span class="fill" style="width:${(v.n / vmax * 100).toFixed(2)}%"></span>
    </span>
    <span class="n">${v.n}</span>
  </div>`).join("") + (DATA.pipeline_only.length ? `
  <p class="hint" style="margin:8px 0 0">Pipeline only, no active blueprint yet:
    ${DATA.pipeline_only.map(p => esc(p.k) + " (" + p.n + ")").join(", ")}.</p>` : "");
document.querySelectorAll("#verts .bar").forEach(b => bindTip(b, b.dataset.tip));

/* ---- field-count histogram ---- */
const BINS = [[1, 25], [26, 50], [51, 75], [76, 100], [101, 150], [151, 200], [201, 400]];
const act = DATA.forms.filter(f => f.st === "active");
const counts = BINS.map(([lo, hi]) => act.filter(f => f.n >= lo && f.n <= hi).length);
const hmax = Math.max(...counts, 1);
el("hist").innerHTML = counts.map((c, i) => `
  <div class="hcol" data-tip="${BINS[i][0]}–${BINS[i][1]} fields: ${c} blueprints">
    <span class="hn">${c}</span>
    <span class="hb" style="height:${(c / hmax * 100).toFixed(1)}%"></span>
  </div>`).join("");
el("haxis").innerHTML = BINS.map(([lo, hi], i) =>
  `<span>${i === BINS.length - 1 ? lo + "+" : lo + "–" + hi}</span>`).join("");
el("histnote").textContent =
  `Median ${S.median} fields; range ${S.fmin}–${S.fmax}. ` +
  `The long tail is the omnibus returns — Form 990, the URLA, CMS-1500.`;
document.querySelectorAll("#hist .hcol").forEach(c => bindTip(c, c.dataset.tip));

/* ---- issuers: top of the roster, remainder folded into one row ---- */
const ISS_SHOWN = 11;
const iss = DATA.issuers.slice(0, ISS_SHOWN);
const rest = DATA.issuers.slice(ISS_SHOWN);
const restN = rest.reduce((a, i) => a + i.n, 0);
const imax = Math.max(...DATA.issuers.map(i => i.n), 1);
el("issuers").innerHTML = iss.map(i => `
  <div class="bar" data-tip="${esc(i.k)}: ${i.n} blueprints">
    <span class="k" title="${esc(i.k)}">${esc(i.k)}</span>
    <span class="track"><span class="fill" style="width:${
      (i.n / imax * 100).toFixed(2)}%"></span></span>
    <span class="n">${i.n}</span>
  </div>`).join("") + (restN ? `
  <div class="bar" data-tip="${rest.length} further issuers, ${restN} blueprints">
    <span class="k" style="color:var(--ink-3)">${rest.length} others</span>
    <span class="track"><span class="fill" style="width:${
      (restN / imax * 100).toFixed(2)}%;background:var(--line-2)"></span></span>
    <span class="n" style="color:var(--ink-3)">${restN}</span>
  </div>` : "");
document.querySelectorAll("#issuers .bar").forEach(b => bindTip(b, b.dataset.tip));

/* ---- canonical bindings ---- */
el("bindings").innerHTML = DATA.bindings.map(b =>
  `<dt>${esc(b.k)}</dt><dd>${b.n}</dd>`).join("") +
  `<dt style="color:var(--ink-3)">no binding</dt><dd style="color:var(--ink-3)">${
    S.active - S.bound}</dd>`;

/* ---- provenance ---- */
const SER = ["var(--s1)", "var(--s2)", "var(--s3)"];
const ptot = DATA.provenance.reduce((a, p) => a + p.n, 0) || 1;
el("provseg").innerHTML = DATA.provenance.map((p, i) =>
  `<i style="flex:${p.n};background:${SER[i % 3]}" data-tip="${esc(p.k)}: ${p.n}"></i>`).join("");
el("provleg").innerHTML = DATA.provenance.map((p, i) => `
  <div class="lg"><i style="background:${SER[i % 3]}"></i>
    <span class="lk">${esc(p.k)}</span>
    <span class="ln">${p.n} &middot; ${(p.n / ptot * 100).toFixed(0)}%</span></div>`).join("");
document.querySelectorAll("#provseg i").forEach(s => bindTip(s, s.dataset.tip));

/* ---- validation callout ---- */
el("callout").innerHTML = `
  <p><strong>${S.eb_active} of ${S.active} active blueprints have ExtractBench
  cases attached</strong> (${S.eb_refs_active} case refs), and
  <strong>${S.evaluated} has a recorded eval run</strong>. This is the thin part
  of the library: the blueprints exist and are well formed, but almost none of
  them have a score against held-out documents.</p>
  <p>A further ${S.eb_pipeline} ExtractBench-referenced forms sit in the pipeline
  rather than the library, so ${S.eb_refs_all} case refs are on the books in
  total &mdash; the corpus is further along than the scoring.</p>
  <div class="evrow">${DATA.evals.flatMap(f => f.ev.map(e =>
    `<span class="ev">${esc(f.id)} &middot; ${esc(e.c)} &middot; <b>${
      e.s.toFixed(3)}</b>${e.n ? " (" + e.n + " cases)" : ""}</span>`)).join("")}</div>`;

/* ---- table ---- */
const FORMS = DATA.forms;
for (const [id, key] of Object.entries({ fst: "st", fv: "v", fb: "bl" })) {
  const vals = [...new Set(FORMS.map(f => f[key]).filter(Boolean))].sort();
  for (const v of vals) el(id).add(new Option(v, v));
}
let sk = "id", asc = true;
function flags(f) {
  const p = [];
  if (f.wm) p.push("wmap");
  if (f.d11) p.push("v1.1");
  if (f.site) p.push("site");
  if (f.eb) p.push(`<b>EB ${f.eb}</b>`);
  if (f.ev.length) p.push(`<b>eval</b>`);
  return `<span class="flags">${p.join(" ")}</span>`;
}
function row(f) {
  const name = LINKS && f.path
    ? `<a href="../${esc(f.path)}">${esc(f.id)}</a>` : esc(f.id);
  return `<tr>
    <td class="id">${name}</td>
    <td class="t">${esc(f.t) || `<span style="color:var(--ink-3)">${esc(f.note)}</span>`}</td>
    <td>${esc(f.iss)}</td>
    <td>${esc(f.v)}</td>
    <td class="num">${f.n || ""}</td>
    <td>${f.bl ? `<span class="chip bind">${esc(f.bl)}</span>` : ""}</td>
    <td><span class="chip ${f.st}">${esc(f.st.replace("_", " "))}</span></td>
    <td class="num">${flags(f)}</td></tr>`;
}
function apply() {
  const q = el("q").value.trim().toLowerCase();
  const st = el("fst").value, vt = el("fv").value;
  const bd = el("fb").value, fl = el("ff").value;
  let rows = FORMS.filter(f => {
    if (st && f.st !== st) return false;
    if (vt && f.v !== vt) return false;
    if (bd && f.bl !== bd) return false;
    if (fl === "bound" && !f.b) return false;
    if (fl === "unbound" && f.b) return false;
    if (fl === "wm" && !f.wm) return false;
    if (fl === "d11" && !f.d11) return false;
    if (fl === "eb" && !f.eb) return false;
    if (fl === "ev" && !f.ev.length) return false;
    if (q) {
      const hay = [f.id, f.t, f.iss, f.v, f.j, f.bl, f.p, f.note,
        f.tags.join(" "), f.al.join(" ")].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  rows.sort((a, b) => {
    const x = a[sk], y = b[sk];
    const c = typeof x === "number" ? (x || 0) - (y || 0)
      : String(x || "").localeCompare(String(y || ""));
    return asc ? c : -c;
  });
  el("tb").innerHTML = rows.length
    ? rows.map(row).join("")
    : `<tr><td colspan="8" class="empty">No form matches those filters.</td></tr>`;
  el("tally").textContent = `${rows.length} of ${FORMS.length} forms`;
}
for (const id of ["q", "fst", "fv", "fb", "ff"])
  el(id).addEventListener("input", apply);
document.querySelectorAll("th[data-k]").forEach(th => {
  th.tabIndex = 0;
  const go = () => {
    const k = th.dataset.k;
    asc = sk === k ? !asc : (k === "n" || k === "eb" ? false : true);
    sk = k;
    document.querySelectorAll("th[data-k] .ar").forEach(a => a.remove());
    th.insertAdjacentHTML("beforeend",
      `<span class="ar"> ${asc ? "↑" : "↓"}</span>`);
    apply();
  };
  th.addEventListener("click", go);
  th.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
  });
});
apply();
</script>
"""

SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
__PAGE__
</body>
</html>
"""


def main() -> None:
    data = collect()
    body = PAGE.replace("__GENERATED__", data["generated"]).replace(
        "__DATA__", json.dumps(data, separators=(",", ":")))

    standalone = SHELL.replace("__PAGE__", body.replace("__LINKS__", "true", 1))
    # insert <body> after the </style> block's closing tag for valid nesting
    standalone = standalone.replace("</style>\n", "</style>\n</head>\n<body>\n", 1)
    OUT_STANDALONE.write_text(standalone)

    OUT_ARTIFACT.write_text(body.replace("__LINKS__", "false", 1))

    print(f"wrote {OUT_STANDALONE} ({len(standalone) // 1024} KB)")
    print(f"wrote {OUT_ARTIFACT} ({len(OUT_ARTIFACT.read_text()) // 1024} KB)")
    print(f"     {data['stats']['active']} active, {len(data['forms'])} tracked")


if __name__ == "__main__":
    main()
