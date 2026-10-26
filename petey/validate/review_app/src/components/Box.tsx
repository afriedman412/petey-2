// A box drawn on the page image at a rect in PDF points. The page is drawn `zoom` pixels to the point, so the scale
// is the zoom (the old page measured the image for it).
import { createContext, useContext, type CSSProperties, type HTMLAttributes, type ReactNode } from 'react';
import type { Rect } from '../lib/util';

export const ScaleContext = createContext(1);
export const useScale = () => useContext(ScaleContext);

export function boxStyle(r: Rect, s: number, pad = 0, min = 5): CSSProperties {
  return {
    left: (r[0] - pad) * s, top: (r[1] - pad) * s,
    width: Math.max(min, (r[2] - r[0] + 2 * pad) * s), height: Math.max(min, (r[3] - r[1] + 2 * pad) * s),
  };
}

type Props = HTMLAttributes<HTMLDivElement> & {
  rect: Rect; pad?: number; min?: number; color?: string; vars?: Record<string, string>; children?: ReactNode;
  [data: `data-${string}`]: string | number | undefined;
};

export function Box({ rect, pad = 0, min = 5, color, vars, style, children, ...rest }: Props) {
  const s = useScale();
  const v: Record<string, string> = { ...(color ? { '--c': color } : {}), ...vars };
  return <div {...rest} style={{ ...boxStyle(rect, s, pad, min), ...v, ...style } as CSSProperties}>{children}</div>;
}

/** A grid's or a block's outline in round dots (an SVG, so the dots are round at any size). */
export function Dots({ w, h }: { w: number; h: number }) {
  return <svg width={w} height={h} className="gtsvg"><rect x={2} y={2} width={Math.max(0, w - 4)} height={Math.max(0, h - 4)} rx={4} /></svg>;
}
