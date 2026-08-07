import type { AppState } from "../shared/contracts";
import { serviceStateLabel, serviceStateTone } from "../shared/service-state";
import { element, hydrateIcons, setIconButton, setTone } from "./components";

/**
 * Renderer for the compact tray popover. Deliberately minimal: it reuses the
 * same typed `window.arthur` API and IPC channel as the main panel (no new
 * runtime-control IPC), never renders transcript content, and is entirely
 * click-driven with no polling of its own.
 */

const serviceDot = element("service-dot");
const serviceLabel = element("service-label");
const lastAction = element<HTMLParagraphElement>("last-action");
const listenToggle = element<HTMLButtonElement>("listen-toggle");
const openSettings = element<HTMLButtonElement>("open-settings");

let busy = false;

function renderState(state: AppState): void {
  const tone = serviceStateTone(state.service);
  const running = state.runtimePid !== null;

  serviceLabel.textContent = serviceStateLabel(state.service);
  setTone(serviceDot, tone);
  lastAction.textContent = state.statusMessage || "No recent action.";

  listenToggle.dataset.running = String(running);
  listenToggle.setAttribute("aria-pressed", String(running));
  setIconButton(listenToggle, running ? "stop" : "play", running ? "Pause" : "Listen");
  listenToggle.disabled = busy;
}

function renderError(error: unknown): void {
  console.error("Arthur popover could not reach the runtime.", error);
  lastAction.textContent = error instanceof Error ? error.message : String(error);
  setTone(serviceDot, "danger");
}

async function toggleListening(): Promise<void> {
  if (busy) return;
  busy = true;
  listenToggle.disabled = true;
  try {
    const state = await window.arthur.getState();
    const running = state.runtimePid !== null;
    renderState(running ? await window.arthur.stopRuntime() : await window.arthur.startRuntime());
  } catch (error) {
    renderError(error);
  } finally {
    busy = false;
    listenToggle.disabled = false;
  }
}

async function initialize(): Promise<void> {
  try {
    renderState(await window.arthur.getState());
  } catch (error) {
    renderError(error);
  }
}

hydrateIcons();
listenToggle.addEventListener("click", () => {
  void toggleListening();
});
openSettings.addEventListener("click", () => {
  window.arthur.showMainWindow();
});
window.arthur.onStateChanged(renderState);
void initialize();
