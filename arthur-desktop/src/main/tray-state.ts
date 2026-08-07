import type { AppState, ServiceState } from "../shared/contracts";
import {
  serviceStateLabel,
  serviceVisualState,
  type ServiceVisualState,
} from "../shared/service-state";

/**
 * Reduces every runtime service state to one of four tray icon presentations.
 * Kept deliberately small so the tray never needs more than a handful of
 * distinguishable icon assets. This is the same reduction the floating widget
 * uses (`serviceVisualState` in `shared/service-state.ts`), aliased here so
 * existing tray call sites and tests are unaffected.
 */
export type TrayVisualState = ServiceVisualState;

export function trayVisualStateFor(service: ServiceState): TrayVisualState {
  return serviceVisualState(service);
}

/** Concise tray tooltip text. No em dashes, matching Arthur's copy style. */
export function trayTooltipFor(state: AppState): string {
  return `Arthur: ${serviceStateLabel(state.service)}`;
}

export function runtimeIsRunning(state: AppState): boolean {
  return state.runtimePid !== null;
}

/**
 * Framework-agnostic description of a tray context menu item. Kept free of any
 * Electron types so the mapping logic can be unit tested without a running
 * Electron process; the tray controller adapts this to Electron's
 * `MenuItemConstructorOptions` shape.
 */
export interface TrayMenuItem {
  readonly label?: string;
  readonly separator?: true;
  readonly enabled?: boolean;
  readonly click?: () => void;
}

export interface TrayMenuActions {
  readonly onShowArthur: () => void;
  readonly onToggleRuntime: () => void;
  readonly onRestart: () => void;
  readonly onQuit: () => void;
}

/** Builds the tray context menu template from the current AppState. */
export function buildTrayMenuTemplate(
  state: AppState,
  actions: TrayMenuActions,
): TrayMenuItem[] {
  const running = runtimeIsRunning(state);
  return [
    { label: "Show Arthur", click: actions.onShowArthur },
    { separator: true },
    {
      label: running ? "Stop listening" : "Start listening",
      click: actions.onToggleRuntime,
    },
    { label: "Restart", enabled: running, click: actions.onRestart },
    { separator: true },
    { label: "Quit", click: actions.onQuit },
  ];
}
