// Drag and drop on the page and in the sidebar (HTML5 drag and drop, as the old page): a thing dragged carries
// "<kind>:<id>", a target takes the kinds it knows. The outline under the mouse gets .over, the thing dragged
// .dragging (classes on the element itself: they only last the drag).
import type { DragEvent } from 'react';
import { toast } from '../state/actions';

export function dragProps(kind: string, id: string | number, enabled = true) {
  if (!enabled) return { draggable: false };
  return {
    draggable: true,
    onDragStart: (e: DragEvent<HTMLElement>) => {
      e.stopPropagation();
      e.dataTransfer.setData('text/plain', `${kind}:${id}`);
      e.dataTransfer.effectAllowed = 'move';
      e.currentTarget.classList.add('dragging');
    },
    onDragEnd: (e: DragEvent<HTMLElement>) => e.currentTarget.classList.remove('dragging'),
  };
}

/** A drop target for the kinds given: fn(kind, id) for what was dropped. */
export function dropProps(kinds: string[], fn: (kind: string, id: string) => void) {
  return {
    onDragOver: (e: DragEvent<HTMLElement>) => { e.preventDefault(); e.stopPropagation(); e.currentTarget.classList.add('over'); },
    onDragLeave: (e: DragEvent<HTMLElement>) => e.currentTarget.classList.remove('over'),
    onDrop: (e: DragEvent<HTMLElement>) => {
      e.preventDefault(); e.stopPropagation(); e.currentTarget.classList.remove('over');
      const d = e.dataTransfer.getData('text/plain'), i = d.indexOf(':');
      const kind = d.slice(0, i), id = d.slice(i + 1);
      if (kinds.includes(kind)) fn(kind, id);
    },
  };
}

/** A reference copied to the clipboard (a field's, a grid's, a block's), said in the toast. */
export async function copyText(ref: string) {
  try { await navigator.clipboard.writeText(ref); }
  catch { const t = document.createElement('textarea'); t.value = ref; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove(); }
  toast(`Copied ${ref}`);
}
