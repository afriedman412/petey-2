// The tabs, in the order of their buttons and Shift+1..6.
import type { ModeId } from '../lib/types';
import type { ModeDef } from './types';
import { review } from './review';
import { groups } from './groups';
import { add } from './add';
import { grids } from './grids';
import { blocks } from './blocks';
import { audit } from './audit';

export const MODES: Record<ModeId, ModeDef> = { review, groups, add, grids, blocks, audit };
