"""Render registry.db to a self-contained static HTML report.

  widget-mapper/venv/bin/python registry/render_html.py
  → registry/report.html  (open in any browser; no server needed)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry as R

OUT = Path(__file__).resolve().parent / "report.html"


def collect() -> dict:
    conn = R.connect(readonly=True)
    forms = []
    for r in conn.execute("""
        SELECT f.form_id, f.title, f.description, f.status, f.vertical,
               f.jurisdiction, f.issuer, f.site_published,
               MAX(CASE WHEN a.kind='bpt' AND a.spec_version='1.0' THEN 1 ELSE 0 END) v10,
               MAX(CASE WHEN a.kind='bpt' AND a.spec_version='1.1' THEN 1 ELSE 0 END) v11,
               MAX(CASE WHEN a.kind='widget_map' THEN 1 ELSE 0 END) wmap,
               (SELECT COUNT(*) FROM external_refs e
                 WHERE e.form_id=f.form_id AND e.source='extractbench') eb,
               (SELECT GROUP_CONCAT(tag, ' ') FROM form_tags t
                 WHERE t.form_id=f.form_id) tags
        FROM forms f LEFT JOIN artifacts a ON a.form_id=f.form_id
        GROUP BY f.form_id ORDER BY f.form_id"""):
        d = dict(r)
        desc = (d.pop("description") or "")
        d["blurb"] = (d.pop("title") or desc)[:140]
        forms.append(d)
    pdfs = [dict(r) for r in conn.execute("""
        SELECT vertical, COUNT(*) n, SUM(fillable) fillable,
               SUM(status='identified') identified,
               SUM(status='excluded') excluded
        FROM source_pdfs GROUP BY vertical ORDER BY n DESC""")]
    stats = dict(conn.execute("""
        SELECT (SELECT COUNT(*) FROM forms WHERE status='active'),
               (SELECT COUNT(*) FROM forms WHERE status='in_progress'),
               (SELECT COUNT(*) FROM forms WHERE status='planned'),
               (SELECT COUNT(*) FROM source_pdfs),
               (SELECT COUNT(*) FROM external_refs WHERE source='extractbench')
        """).fetchone() and zip(
        ["active", "in_progress", "planned", "pdfs", "eb"],
        conn.execute("""
        SELECT (SELECT COUNT(*) FROM forms WHERE status='active'),
               (SELECT COUNT(*) FROM forms WHERE status='in_progress'),
               (SELECT COUNT(*) FROM forms WHERE status='planned'),
               (SELECT COUNT(*) FROM source_pdfs),
               (SELECT COUNT(*) FROM external_refs WHERE source='extractbench')
        """).fetchone()))
    return {"forms": forms, "pdfs": pdfs, "stats": stats,
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}


HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Petey Blueprint Registry</title>
<style>
:root {
  --bg:#faf9f7; --surface:#fff; --ink:#1a1a1a; --ink2:#5f5c57; --line:#e4e1dc;
  --chip:#efedea; --good-bg:#dcefe2; --good-ink:#1d5c33; --warn-bg:#fdeecb;
  --warn-ink:#7a5310; --plan-bg:#e3e9f5; --plan-ink:#2f4875; --accent:#3d6ad6;
}
@media (prefers-color-scheme: dark) { :root {
  --bg:#16161a; --surface:#1f1f24; --ink:#ebe9e6; --ink2:#a3a09b; --line:#33333a;
  --chip:#2a2a30; --good-bg:#1d3a28; --good-ink:#8fd6a8; --warn-bg:#3d3013;
  --warn-ink:#e5c377; --plan-bg:#232f47; --plan-ink:#9db4e6; --accent:#7d9ff0;
}}
* { box-sizing:border-box; margin:0 }
body { background:var(--bg); color:var(--ink);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; padding:32px 24px }
.wrap { max-width:1200px; margin:0 auto }
h1 { font-size:20px; margin-bottom:4px } .sub { color:var(--ink2); margin-bottom:24px }
.tiles { display:flex; flex-wrap:wrap; gap:12px; margin-bottom:28px }
.tile { background:var(--surface); border:1px solid var(--line); border-radius:8px;
  padding:12px 18px; min-width:130px }
.tile b { display:block; font-size:24px; font-weight:600 }
.tile span { color:var(--ink2); font-size:12px }
.filters { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:14px }
.filters input, .filters select { background:var(--surface); color:var(--ink);
  border:1px solid var(--line); border-radius:6px; padding:7px 10px; font:inherit }
.filters input { width:260px }
.count { color:var(--ink2); align-self:center; font-size:13px }
.tblwrap { overflow-x:auto; background:var(--surface); border:1px solid var(--line);
  border-radius:8px; margin-bottom:32px }
table { border-collapse:collapse; width:100%; font-size:13px }
th { text-align:left; padding:9px 12px; border-bottom:1px solid var(--line);
  color:var(--ink2); font-weight:600; white-space:nowrap; cursor:pointer;
  position:sticky; top:0; background:var(--surface) }
td { padding:7px 12px; border-bottom:1px solid var(--line); vertical-align:top }
tr:last-child td { border-bottom:none }
.id { font-family:ui-monospace,Menlo,monospace; font-size:12.5px; white-space:nowrap }
.blurb { color:var(--ink2); max-width:380px }
.chip { display:inline-block; padding:1px 8px; border-radius:10px; font-size:11.5px;
  background:var(--chip); white-space:nowrap; margin:1px 2px 1px 0 }
.st-active { background:var(--good-bg); color:var(--good-ink) }
.st-in_progress { background:var(--warn-bg); color:var(--warn-ink) }
.st-planned { background:var(--plan-bg); color:var(--plan-ink) }
.layer { font-family:ui-monospace,Menlo,monospace; font-size:11px }
.num { text-align:right; font-variant-numeric:tabular-nums }
h2 { font-size:16px; margin:8px 0 12px }
footer { color:var(--ink2); font-size:12px; margin-top:8px }
</style></head><body><div class="wrap">
<h1>Petey Blueprint Registry</h1>
<div class="sub">generated __GENERATED__ · registry/report.html — regenerate with render_html.py</div>
<div class="tiles" id="tiles"></div>
<div class="filters">
  <input id="q" type="search" placeholder="filter forms… (id, issuer, tag, text)">
  <select id="fstatus"><option value="">status: all</option></select>
  <select id="fvert"><option value="">vertical: all</option></select>
  <select id="flayer"><option value="">layer: all</option>
    <option value="v10">has 1.0</option><option value="v11">has 1.1</option>
    <option value="both">1.0 + 1.1</option><option value="none">no bpt</option>
    <option value="eb">has ExtractBench cases</option></select>
  <span class="count" id="count"></span>
</div>
<div class="tblwrap"><table id="tbl"><thead><tr>
<th data-k="form_id">form_id</th><th data-k="status">status</th>
<th data-k="vertical">vertical</th><th data-k="jurisdiction">jurisdiction</th>
<th data-k="issuer">issuer</th><th>layers</th>
<th data-k="eb" class="num">EB cases</th><th data-k="blurb">description / tags</th>
</tr></thead><tbody></tbody></table></div>
<h2>Source PDFs by directory</h2>
<div class="tblwrap"><table><thead><tr><th>directory</th>
<th class="num">PDFs</th><th class="num">fillable</th><th class="num">identified</th>
<th class="num">excluded</th></tr></thead><tbody id="pdfs"></tbody></table></div>
<footer>SQLite is authoritative (registry/registry.db); this page is a read-only render.</footer>
</div>
<script>
const DATA = __DATA__;
const esc = s => String(s ?? "").replace(/[&<>"]/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const tiles = [["active blueprints", DATA.stats.active],
  ["in progress (1.1-only)", DATA.stats.in_progress],
  ["planned", DATA.stats.planned], ["source PDFs", DATA.stats.pdfs],
  ["ExtractBench cases", DATA.stats.eb]];
document.getElementById("tiles").innerHTML = tiles.map(
  ([l, v]) => `<div class="tile"><b>${v}</b><span>${esc(l)}</span></div>`).join("");
document.getElementById("pdfs").innerHTML = DATA.pdfs.map(p =>
  `<tr><td class="id">${esc(p.vertical)}</td><td class="num">${p.n}</td>
   <td class="num">${p.fillable}</td><td class="num">${p.identified}</td>
   <td class="num">${p.excluded}</td></tr>`).join("");
const sels = { fstatus: "status", fvert: "vertical" };
for (const [id, key] of Object.entries(sels)) {
  const vals = [...new Set(DATA.forms.map(f => f[key]).filter(Boolean))].sort();
  const sel = document.getElementById(id);
  for (const v of vals) sel.add(new Option(v, v));
}
let sortK = "form_id", sortAsc = true;
function layerCell(f) {
  const parts = [];
  if (f.v10) parts.push("1.0"); if (f.v11) parts.push("1.1");
  if (f.wmap) parts.push("wmap"); if (f.site_published) parts.push("site");
  return parts.map(p => `<span class="chip layer">${p}</span>`).join("");
}
function row(f) {
  return `<tr><td class="id">${esc(f.form_id)}</td>
  <td><span class="chip st-${f.status}">${esc(f.status)}</span></td>
  <td>${esc(f.vertical)}</td><td>${esc(f.jurisdiction)}</td>
  <td>${esc(f.issuer)}</td><td>${layerCell(f)}</td>
  <td class="num">${f.eb || ""}</td>
  <td class="blurb">${esc(f.blurb)}${f.tags ?
    " " + f.tags.split(" ").map(t => `<span class="chip">${esc(t)}</span>`).join("") : ""}</td>
  </tr>`;
}
function apply() {
  const q = document.getElementById("q").value.toLowerCase();
  const st = document.getElementById("fstatus").value;
  const vt = document.getElementById("fvert").value;
  const ly = document.getElementById("flayer").value;
  let rows = DATA.forms.filter(f => {
    if (st && f.status !== st) return false;
    if (vt && f.vertical !== vt) return false;
    if (ly === "v10" && !f.v10) return false;
    if (ly === "v11" && !f.v11) return false;
    if (ly === "both" && !(f.v10 && f.v11)) return false;
    if (ly === "none" && (f.v10 || f.v11)) return false;
    if (ly === "eb" && !f.eb) return false;
    if (q) {
      const hay = [f.form_id, f.issuer, f.vertical, f.jurisdiction, f.blurb,
        f.tags].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  rows.sort((a, b) => {
    const x = a[sortK] ?? "", y = b[sortK] ?? "";
    const c = typeof x === "number" || typeof y === "number"
      ? (x || 0) - (y || 0) : String(x).localeCompare(String(y));
    return sortAsc ? c : -c;
  });
  document.querySelector("#tbl tbody").innerHTML = rows.map(row).join("");
  document.getElementById("count").textContent =
    `${rows.length} / ${DATA.forms.length} forms`;
}
for (const el of ["q", "fstatus", "fvert", "flayer"])
  document.getElementById(el).addEventListener("input", apply);
document.querySelectorAll("th[data-k]").forEach(th =>
  th.addEventListener("click", () => {
    const k = th.dataset.k;
    sortAsc = sortK === k ? !sortAsc : true; sortK = k; apply();
  }));
apply();
</script></body></html>
"""


def main() -> None:
    data = collect()
    html = HTML.replace("__GENERATED__", data["generated"]).replace(
        "__DATA__", json.dumps(data, separators=(",", ":")))
    OUT.write_text(html)
    print(f"wrote {OUT} ({len(html)//1024} KB, {len(data['forms'])} forms)")


if __name__ == "__main__":
    main()
