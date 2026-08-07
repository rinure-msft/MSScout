/**
 * Pure geometry for placing the compact tray popover. Kept independent of
 * Electron's types so it can be unit tested directly; the tray popover window
 * passes Electron's `Rectangle` values in, which are structurally compatible.
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

export interface PopoverPositionOptions {
  readonly gap?: number;
  readonly margin?: number;
}

export type ScreenEdge = "top" | "bottom" | "left" | "right";

const DEFAULT_GAP = 8;
const DEFAULT_MARGIN = 8;

function clamp(value: number, min: number, max: number): number {
  if (max < min) return min;
  return Math.min(Math.max(value, min), max);
}

/**
 * The taskbar occupies the gap between a display's full bounds and its work
 * area. The tray icon lives in that gap, so whichever side of the work area
 * the tray icon centre falls outside of identifies where the taskbar (and
 * therefore the tray icon) sits.
 */
export function resolveTaskbarEdge(trayBounds: Rectangle, workArea: Rectangle): ScreenEdge {
  const trayCenterX = trayBounds.x + trayBounds.width / 2;
  const trayCenterY = trayBounds.y + trayBounds.height / 2;
  if (trayCenterY >= workArea.y + workArea.height) return "bottom";
  if (trayCenterY <= workArea.y) return "top";
  if (trayCenterX >= workArea.x + workArea.width) return "right";
  if (trayCenterX <= workArea.x) return "left";
  return "bottom";
}

/**
 * Computes the popover's top-left position next to the tray icon, clamped to
 * the display's work area so the popover never renders off-screen or under
 * the taskbar.
 */
export function computePopoverPosition(
  trayBounds: Rectangle,
  workArea: Rectangle,
  popoverSize: Size,
  options: PopoverPositionOptions = {},
): { x: number; y: number } {
  const gap = options.gap ?? DEFAULT_GAP;
  const margin = options.margin ?? DEFAULT_MARGIN;
  const edge = resolveTaskbarEdge(trayBounds, workArea);
  const trayCenterX = trayBounds.x + trayBounds.width / 2;
  const trayCenterY = trayBounds.y + trayBounds.height / 2;

  const minX = workArea.x + margin;
  const maxX = workArea.x + workArea.width - popoverSize.width - margin;
  const minY = workArea.y + margin;
  const maxY = workArea.y + workArea.height - popoverSize.height - margin;

  if (edge === "bottom") {
    return {
      x: clamp(trayCenterX - popoverSize.width / 2, minX, maxX),
      y: clamp(trayBounds.y - popoverSize.height - gap, minY, maxY),
    };
  }
  if (edge === "top") {
    return {
      x: clamp(trayCenterX - popoverSize.width / 2, minX, maxX),
      y: clamp(trayBounds.y + trayBounds.height + gap, minY, maxY),
    };
  }
  if (edge === "left") {
    return {
      x: clamp(trayBounds.x + trayBounds.width + gap, minX, maxX),
      y: clamp(trayCenterY - popoverSize.height / 2, minY, maxY),
    };
  }
  return {
    x: clamp(trayBounds.x - popoverSize.width - gap, minX, maxX),
    y: clamp(trayCenterY - popoverSize.height / 2, minY, maxY),
  };
}
