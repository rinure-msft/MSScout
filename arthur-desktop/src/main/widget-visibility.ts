/**
 * Pure visibility rules shared by the main process for the floating widget
 * and, by extension, the popover it anchors. Kept free of Electron so the
 * decisions can be unit tested without a running window.
 */

export interface WidgetVisibilityInput {
  /** The user's "Show floating indicator" preference. */
  readonly preferenceEnabled: boolean;
  /** Whether the full settings panel is currently visible. */
  readonly isMainWindowVisible: boolean;
}

/**
 * The floating widget is shown only when the preference is enabled and the
 * full settings panel is not currently visible: showing the panel always
 * hides the widget, and hiding the panel (by Close, Minimise or a hidden
 * startup) shows the widget only if the preference allows it.
 */
export function shouldShowFloatingWidget(input: WidgetVisibilityInput): boolean {
  return input.preferenceEnabled && !input.isMainWindowVisible;
}

/**
 * The tray popover the widget anchors to must never remain open once the
 * full settings panel is visible, regardless of the floating widget
 * preference: the panel and the popover are mutually exclusive surfaces.
 */
export function shouldHidePopoverForMainWindow(isMainWindowVisible: boolean): boolean {
  return isMainWindowVisible;
}
