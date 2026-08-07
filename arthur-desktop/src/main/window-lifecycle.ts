/**
 * Pure window lifecycle helpers shared by the main process. Kept free of
 * Electron imports so they can be unit tested directly.
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

/** Anchors a window to the bottom-right corner of a display's work area. */
export function computeCornerPosition(
  workArea: Rectangle,
  size: Size,
  margin = 12,
): { x: number; y: number } {
  return {
    x: workArea.x + workArea.width - size.width - margin,
    y: workArea.y + workArea.height - size.height - margin,
  };
}

export interface WindowCloseDecision {
  /** When true, the caller should call `event.preventDefault()` and hide the window. */
  readonly shouldHide: boolean;
}

/**
 * Closing the main panel should hide it to the tray rather than quit the
 * application, unless the app is genuinely quitting (tray Quit, or a real
 * shutdown), in which case the window should close as normal.
 */
export function decideWindowClose(isQuitting: boolean): WindowCloseDecision {
  return { shouldHide: !isQuitting };
}

/**
 * Minimising the main panel should hide it to the background experience
 * (the floating widget, when enabled, plus the tray) instead of leaving a
 * minimised entry in the Windows taskbar. Unlike `decideWindowClose`, this is
 * unconditional: minimising is never part of a genuine quit.
 */
export function decideWindowMinimize(): WindowCloseDecision {
  return { shouldHide: true };
}
