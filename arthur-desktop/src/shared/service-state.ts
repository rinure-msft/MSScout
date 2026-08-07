import type { ServiceState } from "./contracts";

export type ServiceTone = "neutral" | "success" | "warning" | "danger";

const SERVICE_STATE_LABELS: Record<ServiceState, string> = {
  activated: "Activated",
  degraded: "Needs attention",
  dictating: "Dictating",
  error: "Error",
  listening: "Listening",
  ready: "Ready",
  starting: "Starting",
  stopped: "Stopped",
};

/** Concise, human-readable label for a runtime service state. */
export function serviceStateLabel(service: ServiceState): string {
  return SERVICE_STATE_LABELS[service];
}

/** Visual tone associated with a runtime service state, shared by every surface. */
export function serviceStateTone(service: ServiceState): ServiceTone {
  if (["listening", "ready", "activated", "dictating"].includes(service)) return "success";
  if (service === "starting") return "warning";
  if (service === "error" || service === "degraded") return "danger";
  return "neutral";
}

/** Whether the assistant is actively responding to a wake or dictating speech. */
export function isActivatedState(service: ServiceState): boolean {
  return service === "activated" || service === "dictating";
}

/**
 * The four presentations every visual surface (tray icon, tray popover accent
 * and the floating widget) reduces a runtime service state to. Kept as one
 * shared mapping so the tray and the floating widget can never drift apart.
 */
export type ServiceVisualState = "stopped" | "listening" | "active" | "error";

const SERVICE_VISUAL_STATES: Record<ServiceState, ServiceVisualState> = {
  starting: "stopped",
  stopped: "stopped",
  ready: "listening",
  listening: "listening",
  activated: "active",
  dictating: "active",
  degraded: "error",
  error: "error",
};

/** Reduces a runtime service state to its shared visual presentation. */
export function serviceVisualState(service: ServiceState): ServiceVisualState {
  return SERVICE_VISUAL_STATES[service];
}

/**
 * True only on the transition into an activated or dictating state, never
 * while remaining in it. Shared by the tray pulse, the optional activation
 * halo and the floating widget's activation bloom so each stays a momentary
 * animation rather than a continuous one.
 */
export function didEnterActivatedState(
  previous: ServiceState | null,
  next: ServiceState,
): boolean {
  if (previous === null) return false;
  if (previous === next) return false;
  return isActivatedState(next) && !isActivatedState(previous);
}

/**
 * Detects a durable activation event even if a short `activated` heartbeat
 * was replaced by `speaking` or `listening` before the desktop poll ran.
 */
export function didActivationIdAdvance(
  previous: string | null,
  next: string | undefined,
): boolean {
  if (previous === null || !next) return false;
  return next !== previous;
}
