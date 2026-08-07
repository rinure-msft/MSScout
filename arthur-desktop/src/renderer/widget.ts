import type { AppState, ServiceState } from "../shared/contracts";
import {
  didActivationIdAdvance,
  serviceStateLabel,
} from "../shared/service-state";
import { widgetRenderContractFor, WIDGET_GLOW_DURATION_MS } from "../shared/widget-visual";
import {
  element,
  hydrateIcons,
  setIcon,
} from "./components";

/**
 * Renderer for the optional floating widget. Deliberately minimal: it never
 * renders transcript or command text, reuses the same typed `window.arthur`
 * API and IPC-driven state updates as the main panel and the popover, and
 * its only interaction is toggling the existing tray popover.
 */

const shell = element<HTMLDivElement>("widget-shell");
const listenButton = element<HTMLButtonElement>("widget-listen");
const openButton = element<HTMLButtonElement>("widget-open");

let previousService: ServiceState | null = null;
let previousActivationId: string | null = null;
let glowTimer: ReturnType<typeof setTimeout> | null = null;
let busy = false;

function renderState(state: AppState): void {
  const contract = widgetRenderContractFor(previousService, state.service);
  shell.dataset.tone = contract.visualState;
  const stateLabel = serviceStateLabel(state.service);
  const running = state.runtimePid !== null;
  setIcon(listenButton, running ? "stop" : "play");
  listenButton.setAttribute(
    "aria-label",
    running ? `Stop listening (${stateLabel})` : `Start listening (${stateLabel})`,
  );
  listenButton.disabled = busy;
  setIcon(openButton, "system");
  openButton.setAttribute("aria-label", `Open Arthur controls (${stateLabel})`);

  if (
    contract.showGlow
    || didActivationIdAdvance(previousActivationId, state.activationId)
  ) {
    if (glowTimer) clearTimeout(glowTimer);
    shell.dataset.glow = "false";
    // Force a reflow so the animation restarts even for back-to-back activations.
    void shell.offsetWidth;
    shell.dataset.glow = "true";
    glowTimer = setTimeout(() => {
      shell.dataset.glow = "false";
      glowTimer = null;
    }, WIDGET_GLOW_DURATION_MS);
  }

  previousService = state.service;
  previousActivationId = state.activationId;
}

function renderError(error: unknown): void {
  console.error("Arthur widget could not reach the runtime.", error);
  shell.dataset.tone = "error";
  setIcon(listenButton, "shield");
  listenButton.setAttribute("aria-label", "Arthur needs attention");
}

hydrateIcons();
listenButton.addEventListener("click", () => {
  void toggleListening();
});
openButton.addEventListener("click", () => {
  window.arthur.showMainWindow();
});

async function toggleListening(): Promise<void> {
  if (busy) return;
  busy = true;
  listenButton.disabled = true;
  try {
    const state = await window.arthur.getState();
    renderState(
      state.runtimePid === null
        ? await window.arthur.startRuntime()
        : await window.arthur.stopRuntime(),
    );
  } catch (error) {
    renderError(error);
  } finally {
    busy = false;
    listenButton.disabled = false;
  }
}

async function initialize(): Promise<void> {
  try {
    renderState(await window.arthur.getState());
  } catch (error) {
    renderError(error);
  }
}

window.arthur.onStateChanged(renderState);
void initialize();
