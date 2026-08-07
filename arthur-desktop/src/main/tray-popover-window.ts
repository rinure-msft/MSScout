import { BrowserWindow, screen, type Rectangle } from "electron";
import type { AppState } from "../shared/contracts";
import { IPC_CHANNELS } from "../shared/constants";
import { computePopoverPosition } from "./popover-position";

/** Substantially smaller than the main 404x640 panel. */
export const POPOVER_SIZE = { width: 296, height: 188 } as const;

/**
 * Owns the compact, click-driven tray popover window: a secure, frameless,
 * non-resizable, skip-taskbar surface positioned next to the tray icon. The
 * window is created once and reused across toggles (hidden, not destroyed)
 * so opening it stays instant.
 */
export class TrayPopoverWindow {
  #window: BrowserWindow | null = null;
  readonly #preloadPath: string;
  readonly #htmlPath: string;

  public constructor(preloadPath: string, htmlPath: string) {
    this.#preloadPath = preloadPath;
    this.#htmlPath = htmlPath;
  }

  #ensureWindow(): BrowserWindow {
    const existing = this.#window;
    if (existing && !existing.isDestroyed()) return existing;

    const window = new BrowserWindow({
      width: POPOVER_SIZE.width,
      height: POPOVER_SIZE.height,
      show: false,
      frame: false,
      transparent: true,
      resizable: false,
      movable: false,
      minimizable: false,
      maximizable: false,
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
    window.webContents.on("before-input-event", (_event, input) => {
      if (input.type === "keyDown" && input.key === "Escape") this.hide();
    });
    window.on("blur", () => {
      this.hide();
    });
    window.on("closed", () => {
      if (this.#window === window) this.#window = null;
    });
    void window.loadFile(this.#htmlPath);
    this.#window = window;
    return window;
  }

  public isVisible(): boolean {
    const window = this.#window;
    return window !== null && !window.isDestroyed() && window.isVisible();
  }

  public show(trayBounds: Rectangle): void {
    const window = this.#ensureWindow();
    const display = screen.getDisplayMatching(trayBounds);
    const position = computePopoverPosition(trayBounds, display.workArea, POPOVER_SIZE);
    window.setPosition(Math.round(position.x), Math.round(position.y), false);
    window.show();
    window.focus();
  }

  public hide(): void {
    const window = this.#window;
    if (window && !window.isDestroyed() && window.isVisible()) window.hide();
  }

  public toggle(trayBounds: Rectangle): void {
    if (this.isVisible()) this.hide();
    else this.show(trayBounds);
  }

  public broadcastState(state: AppState): void {
    const window = this.#window;
    if (window && !window.isDestroyed()) {
      window.webContents.send(IPC_CHANNELS.stateChanged, state);
    }
  }

  public destroy(): void {
    const window = this.#window;
    if (window && !window.isDestroyed()) window.destroy();
    this.#window = null;
  }
}
