// Audit: read-only tables of a form's versions and run history, or of the batch; no page image (the sidebar takes
// the width), so no pages and nothing drawn. The tab's definition for the frame.
import type { ModeDef } from '../types';
import { Bar, Panel } from './Panel';
import { key, load, useAudit } from './store';

export const audit: ModeDef = {
  id: 'audit',
  name: 'Audit',
  own: [],
  wide: true,
  help: {
    keys: [['b', 'batch table / this form']],
    tips: ['Read only. Each version of the form: the library copy and any fresh run of the current pipeline, with page-check flags, Jev, name checks and review, per page.',
      'History: generation (petey-master or a fresh run, with cost and minutes per page), validate runs, page checks, Jev, the mechanical pass, hand review, Claude, library commits. Click a line for its details.'],
  },
  load,
  pages: () => [],
  startPage: () => 1,
  pageLabel: () => '',
  useData: () => useAudit(s => s.A),
  Bar, Panel,
  Layer: () => null,
  key,
};
