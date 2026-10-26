// The server's API (blueprint_review.py), unchanged from the old page: JSON in and out, a failed request throws with
// the server's text.

export async function j<T = any>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export const send = <T = any>(method: string, url: string, body?: unknown): Promise<T> =>
  j<T>(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });

/** `/api/<mode>/<form><rest>` */
export const mapi = (m: string, bid: string, rest = '') => `/api/${m}/${encodeURIComponent(bid)}${rest}`;

export const pngUrl = (bid: string, page: number) => `/api/blueprints/${encodeURIComponent(bid)}/png/${page}`;
