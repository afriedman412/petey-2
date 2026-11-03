// A form's status as icons (Andrew, 2026-11-03: "a little V icon and/or a little S icon, instead of all the text"):
// V validated (every name accepted), S structure validated ("accept structure"); a form with both shows both, a
// generated one shows neither; an ignored form (2026-11-03) shows only a grey I, its reason on hover.
export function StatusIcons({ k, v, s, why }: { k?: string; v: boolean; s: boolean; why?: string }) {
  if (k === 'ignored') return <span className="vsicons"><i className="vsic i" title={`ignored: ${why || ''}`}>I</i></span>;
  if (!v && !s) return <span className="dim" title={why ? `generated: ${why}` : 'generated'}>{why ? '·' : ''}</span>;
  return (
    <span className="vsicons">
      {v && <i className="vsic v" title="validated: every name accepted">V</i>}
      {s && <i className="vsic s" title="structure validated: fields, kinds, groups, grids and blocks accepted">S</i>}
    </span>
  );
}
