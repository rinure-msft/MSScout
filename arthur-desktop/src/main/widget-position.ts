/**
 * Pure geometry for placing the floating widget. Kept independent of
 * Electron so it can be unit tested directly; the floating widget window
 * passes Electron's `Rectangle`-shaped `workArea` values in, which are
 * structurally compatible.
 */
export interface Rectangle {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface Size {
  readonly width: number;
  readonly height: number;
}

export interface Point {
  readonly x: number;
  readonly y: number;
}

const DEFAULT_MARGIN = 16;

function clamp(value: number, min: number, max: number): number {
  if (max < min) return min;
  return Math.min(Math.max(value, min), max);
}

/**
 * Default floating widget position: the bottom-right corner of the work
 * area, echoing the corner the main panel itself favours (see
 * `computeCornerPosition` in `window-lifecycle.ts`), so a first launch feels
 * consistent regardless of which surface is visible.
 */
export function defaultWidgetPosition(
  workArea: Rectangle,
  size: Size,
  margin = DEFAULT_MARGIN,
): Point {
  return {
    x: workArea.x + workArea.width - size.width - margin,
    y: workArea.y + workArea.height - size.height - margin,
  };
}

/**
 * Clamps a previously stored (or just-dragged) widget position to a work
 * area so the widget never renders off-screen, including after a monitor is
 * disconnected, resized or rearranged. The caller is responsible for
 * resolving which display's work area applies (typically the display
 * nearest the stored point).
 */
export function clampWidgetPosition(
  position: Point,
  workArea: Rectangle,
  size: Size,
  margin = 0,
): Point {
  const minX = workArea.x + margin;
  const maxX = workArea.x + workArea.width - size.width - margin;
  const minY = workArea.y + margin;
  const maxY = workArea.y + workArea.height - size.height - margin;
  return {
    x: clamp(position.x, minX, maxX),
    y: clamp(position.y, minY, maxY),
  };
}
