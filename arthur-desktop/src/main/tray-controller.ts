import { Menu, Tray, type MenuItemConstructorOptions, type Rectangle } from "electron";
import type { AppState } from "../shared/contracts";
import { TRAY_PULSE_DURATION_MS } from "./activation-pulse";
import { buildTrayIconSet, type TrayIconSet } from "./tray-icon-assets";
import {
  buildTrayMenuTemplate,
  trayTooltipFor,
  trayVisualStateFor,
  type TrayMenuItem,
  type TrayVisualState,
} from "./tray-state";

export interface TrayControllerActions {
  readonly onShowArthur: () => void;
  readonly onStartRuntime: () => void;
  readonly onStopRuntime: () => void;
  readonly onRestartRuntime: () => void;
  readonly onTogglePopover: (trayBounds: Rectangle) => void;
  readonly onQuit: () => void;
}

function toMenuItemOptions(item: TrayMenuItem): MenuItemConstructorOptions {
  return {
    ...(item.label !== undefined ? { label: item.label } : {}),
    ...(item.separator ? { type: "separator" as const } : {}),
    ...(item.enabled !== undefined ? { enabled: item.enabled } : {}),
    ...(item.click !== undefined ? { click: item.click } : {}),
  };
}

/**
 * Owns the real notification-area Tray for the lifetime of the application:
 * icon state, tooltip, context menu and the brief activation pulse. Left as
 * the only module that touches Electron's `Tray` API so the pure mapping
 * logic in `tray-state.ts` stays independently testable.
 */
export class TrayController {
  #tray: Tray | null = null;
  #icons: TrayIconSet | null = null;
  #pulseTimer: NodeJS.Timeout | null = null;
  #lastVisual: TrayVisualState = "stopped";
  readonly #actions: TrayControllerActions;

  public constructor(actions: TrayControllerActions) {
    this.#actions = actions;
  }

  public async initialize(): Promise<void> {
    this.#icons = await buildTrayIconSet();
    const tray = new Tray(this.#icons.stopped);
    tray.setToolTip("Arthur: Preparing");
    tray.on("click", (_event, bounds) => {
      this.#actions.onTogglePopover(bounds);
    });
    this.#tray = tray;
  }

  public isActive(): boolean {
    return this.#tray !== null;
  }

  public getBounds(): Rectangle | null {
    return this.#tray?.getBounds() ?? null;
  }

  /**
   * Updates the tray icon, tooltip and context menu from the latest
   * AppState. `enteredActivatedState` is computed once by the caller so this
   * class never needs its own duplicate state-transition bookkeeping.
   */
  public update(state: AppState, enteredActivatedState: boolean): void {
    const tray = this.#tray;
    const icons = this.#icons;
    if (!tray || !icons) return;

    const visual = trayVisualStateFor(state.service);
    this.#lastVisual = visual;
    if (!this.#pulseTimer) {
      tray.setImage(icons[visual]);
    }
    tray.setToolTip(trayTooltipFor(state));
    tray.setContextMenu(
      Menu.buildFromTemplate(
        buildTrayMenuTemplate(state, {
          onShowArthur: this.#actions.onShowArthur,
          onToggleRuntime: () => {
            if (state.runtimePid !== null) this.#actions.onStopRuntime();
            else this.#actions.onStartRuntime();
          },
          onRestart: this.#actions.onRestartRuntime,
          onQuit: this.#actions.onQuit,
        }).map(toMenuItemOptions),
      ),
    );

    if (enteredActivatedState) this.#pulse();
  }

  #pulse(): void {
    const tray = this.#tray;
    const icons = this.#icons;
    if (!tray || !icons) return;
    if (this.#pulseTimer) clearTimeout(this.#pulseTimer);
    tray.setImage(icons.pulse);
    this.#pulseTimer = setTimeout(() => {
      this.#pulseTimer = null;
      if (this.#tray && this.#icons) this.#tray.setImage(this.#icons[this.#lastVisual]);
    }, TRAY_PULSE_DURATION_MS);
  }

  public destroy(): void {
    if (this.#pulseTimer) {
      clearTimeout(this.#pulseTimer);
      this.#pulseTimer = null;
    }
    this.#tray?.destroy();
    this.#tray = null;
  }
}
