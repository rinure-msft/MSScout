import type { ServiceState } from "./contracts";
import { didEnterActivatedState, serviceVisualState, type ServiceVisualState } from "./service-state";

/** The floating widget shares the same four presentations as the tray icon. */
export type WidgetVisualState = ServiceVisualState;

/**
 * Roughly how long the floating widget's activation bloom animates for, in
 * milliseconds. Chosen to sit close to the halo's own 800ms pulse so every
 * "Arthur just activated" cue feels consistent across surfaces.
 */
export const WIDGET_GLOW_DURATION_MS = 900;

export interface WidgetRenderContract {
  /** Which of the four presentations the widget should show right now. */
  readonly visualState: WidgetVisualState;
  /** Whether a single activation bloom should play for this state update. */
  readonly showGlow: boolean;
}

/**
 * Pure description of what the floating widget should render for a state
 * transition. Kept independent of the DOM and of Electron so it can be unit
 * tested directly; `widget.ts` is the only place that touches the actual
 * element classes and the timer that clears the bloom after
 * `WIDGET_GLOW_DURATION_MS`.
 */
export function widgetRenderContractFor(
  previous: ServiceState | null,
  next: ServiceState,
): WidgetRenderContract {
  return {
    visualState: serviceVisualState(next),
    showGlow: didEnterActivatedState(previous, next),
  };
}
