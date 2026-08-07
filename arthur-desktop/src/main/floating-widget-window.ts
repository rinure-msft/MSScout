import { BrowserWindow, screen } from "electron";
import type { AppState } from "../shared/contracts";
import type { WidgetPosition } from "../shared/schemas";
import { IPC_CHANNELS } from "../shared/constants";
import { clampWidgetPosition, defaultWidgetPosition, type Point } from "./widget-position";

/**
 * Includes transparent breathing room around the visible 104x40 strip so
 * the activation bloom is not clipped by the BrowserWindow bounds.
 */
export const WIDGET_SIZE = { width: 136, height: 72 } as const;

/** Debounce between the last drag movement and persisting the new position. */
const POSITION_PERSIST_DEBOUNCE_MS = 400;

/**
 * Owns the optional floating widget: a tiny, transparent, always-on-top,
 * skip-taskbar surface shown while Arthur is minimised. It reuses the
 * compact tray popover for its interaction (a click toggles it, anchored to
 * the widget's own bounds) and reports drag positions back to the main
 * process via `onPositionChanged`, which is the only writer of the stored
 * position so a later renderer preferences patch can never clobber it.
 */
export class FloatingWidgetWindow {
  #window: BrowserWindow | null = null;
  #moveTimer: NodeJS.Timeout | null = null;
  readonly #preloadPath: string;
  readonly #htmlPath: string;
  readonly #onPositionChanged: (position: Point) => void;

  public constructor(
    preloadPath: string,
    htmlPath: string,
    onPositionChanged: (position: Point) => void,
  ) {
    this.#preloadPath = preloadPath;
    this.#htmlPath = htmlPath;
    this.#onPositionChanged = onPositionChanged;
  }

  #resolveInitialPosition(storedPosition: WidgetPosition): Point {
    if (storedPosition) {
      const display = screen.getDisplayNearestPoint(storedPosition);
      return clampWidgetPosition(storedPosition, display.workArea, WIDGET_SIZE);
    }
    const display = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
    return defaultWidgetPosition(display.workArea, WIDGET_SIZE);
  }

  #ensureWindow(storedPosition: WidgetPosition): BrowserWindow {
    const existing = this.#window;
    if (existing && !existing.isDestroyed()) return existing;

    const position = this.#resolveInitialPosition(storedPosition);
    const window = new BrowserWindow({
      x: position.x,
      y: position.y,
      width: WIDGET_SIZE.width,
      height: WIDGET_SIZE.height,
      show: false,
      frame: false,
      transparent: true,
      hasShadow: false,
      resizable: false,
      movable: true,
      minimizable: false,
      maximizable: false,
      focusable: true,
      skipTaskbar: true,
      alwaysOnTop: true,
      backgroundColor: "#00000000",
      webPreferences: {
        preload: this.#preloadPath,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        webSecurity: true,
      },
    });
    window.setMenuBarVisibility(false);
    window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    window.webContents.on("will-navigate", (event) => {
      event.preventDefault();
    });
    // `move` (rather than `moved`) is used because Electron only reliably
    // emits `moved` at the end of a real mouse-driven drag on Windows; a
    // programmatic `setPosition` call (used by the native smoke test, and a
    // reasonable thing for automation to rely on) only fires `move`. `move`
    // fires continuously while dragging too, which is exactly why the
    // position persistence below is debounced.
    window.on("move", () => {
      if (window.isDestroyed()) return;
      const [x = 0, y = 0] = window.getPosition();
      this.#schedulePositionPersist({ x, y });
    });
    window.on("closed", () => {
      if (this.#window === window) this.#window = null;
    });
    void window.loadFile(this.#htmlPath);
    this.#window = window;
    return window;
  }

  #schedulePositionPersist(position: Point): void {
    if (this.#moveTimer) clearTimeout(this.#moveTimer);
    this.#moveTimer = setTimeout(() => {
      this.#moveTimer = null;
      this.#onPositionChanged(position);
    }, POSITION_PERSIST_DEBOUNCE_MS);
  }

  /**
   * Shows the widget, creating it on first use at `storedPosition` (or a
   * sensible default). On every show, the window's current position is
   * re-clamped to whichever display it now sits nearest to, so a monitor
   * that was disconnected or rearranged while the widget was hidden can
   * never leave it off-screen.
   */
  public show(storedPosition: WidgetPosition): void {
    const window = this.#ensureWindow(storedPosition);
    const [x = 0, y = 0] = window.getPosition();
    const display = screen.getDisplayNearestPoint({ x, y });
    const clamped = clampWidgetPosition({ x, y }, display.workArea, WIDGET_SIZE);
    if (clamped.x !== x || clamped.y !== y) window.setPosition(clamped.x, clamped.y, false);
    if (!window.isVisible()) window.show();
  }

  public hide(): void {
    const window = this.#window;
    if (window && !window.isDestroyed() && window.isVisible()) window.hide();
  }

  public isVisible(): boolean {
    const window = this.#window;
    return window !== null && !window.isDestroyed() && window.isVisible();
  }

  public broadcastState(state: AppState): void {
    const window = this.#window;
    if (window && !window.isDestroyed()) {
      window.webContents.send(IPC_CHANNELS.stateChanged, state);
    }
  }

  public destroy(): void {
    if (this.#moveTimer) {
      clearTimeout(this.#moveTimer);
      this.#moveTimer = null;
    }
    const window = this.#window;
    if (window && !window.isDestroyed()) window.destroy();
    this.#window = null;
  }
}
