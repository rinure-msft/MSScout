import { BrowserWindow, screen, type Rectangle } from "electron";
import { ACTIVATION_HALO_DURATION_MS } from "./activation-pulse";

/**
 * Owns the optional activation halo: a restrained, click-through, transparent
 * edge overlay shown on the active display only for the brief moment Arthur
 * activates. Recreated per pulse and disposed afterwards so it never
 * persists while merely listening.
 */
export class ActivationHaloWindow {
  #window: BrowserWindow | null = null;
  #hideTimer: NodeJS.Timeout | null = null;
  readonly #htmlPath: string;

  public constructor(htmlPath: string) {
    this.#htmlPath = htmlPath;
  }

  /**
   * Shows the halo on the display matching `activeBounds` (the main window's
   * bounds when visible), falling back to the display under the cursor.
   */
  public pulse(activeBounds: Rectangle | null): void {
    this.destroy();
    const display = activeBounds
      ? screen.getDisplayMatching(activeBounds)
      : screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
    const window = this.#create(display.bounds);
    window.once("ready-to-show", () => {
      if (window.isDestroyed() || this.#window !== window) return;
      window.showInactive();
      this.#hideTimer = setTimeout(() => {
        this.#hideTimer = null;
        this.destroy();
      }, ACTIVATION_HALO_DURATION_MS);
    });
  }

  #create(bounds: Rectangle): BrowserWindow {
    const window = new BrowserWindow({
      ...bounds,
      show: false,
      frame: false,
      transparent: true,
      hasShadow: false,
      resizable: false,
      movable: false,
      minimizable: false,
      maximizable: false,
      focusable: false,
      skipTaskbar: true,
      alwaysOnTop: true,
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
      },
    });
    window.setIgnoreMouseEvents(true);
    window.setAlwaysOnTop(true, "screen-saver");
    window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    window.webContents.on("will-navigate", (event) => {
      event.preventDefault();
    });
    window.on("closed", () => {
      if (this.#window === window) this.#window = null;
    });
    void window.loadFile(this.#htmlPath);
    this.#window = window;
    return window;
  }

  public destroy(): void {
    if (this.#hideTimer) {
      clearTimeout(this.#hideTimer);
      this.#hideTimer = null;
    }
    const window = this.#window;
    if (window && !window.isDestroyed()) window.destroy();
    this.#window = null;
  }
}
