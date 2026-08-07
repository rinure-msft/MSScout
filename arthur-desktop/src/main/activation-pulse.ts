import {
  didActivationIdAdvance,
  didEnterActivatedState,
} from "../shared/service-state";

/**
 * Re-exported from `shared/service-state.ts`, which also backs the floating
 * widget's activation bloom, so there is exactly one "did we just activate"
 * rule shared by every surface.
 */
export { didActivationIdAdvance, didEnterActivatedState };

/** Tray icon pulse duration, kept within the 600-900ms envelope. */
export const TRAY_PULSE_DURATION_MS = 750;

/** How long the optional activation halo remains visible for a single pulse. */
export const ACTIVATION_HALO_DURATION_MS = 800;

/** Whether the optional activation halo should be shown for this transition. */
export function shouldPulseActivationHalo(
  showActivationHaloPreference: boolean,
  enteredActivatedState: boolean,
): boolean {
  return showActivationHaloPreference && enteredActivatedState;
}
