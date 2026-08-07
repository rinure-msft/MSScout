import type {
  DesktopPreferences,
  DesktopPreferencesPatch,
  Microphone,
  RuntimeSettings,
  RuntimeSettingsPatch,
  VoiceOption,
  VoiceSettings,
} from "../shared/schemas";
import type { AppState } from "../shared/contracts";
import { serviceStateLabel, serviceStateTone } from "../shared/service-state";
import {
  element,
  hydrateIcons,
  setIconButton,
  setTone,
  type Tone,
} from "./components";

const PANEL_NAMES = ["voice", "profile", "microphone", "system"] as const;
type PanelName = typeof PANEL_NAMES[number];

const operationMessage = element<HTMLParagraphElement>("operation-message");
const voiceProvider = element<HTMLSelectElement>("voice-provider");
const voiceLocale = element<HTMLSelectElement>("voice-locale");
const voiceSelect = element<HTMLSelectElement>("voice-select");
const edgeControls = element("edge-controls");
const windowsControls = element("windows-controls");
const edgeRate = element<HTMLInputElement>("edge-rate");
const edgePitch = element<HTMLInputElement>("edge-pitch");
const edgeVolume = element<HTMLInputElement>("edge-volume");
const windowsRate = element<HTMLInputElement>("windows-rate");
const windowsVolume = element<HTMLInputElement>("windows-volume");
const microphoneSelect = element<HTMLSelectElement>("microphone-select");
const runtimeToggle = element<HTMLButtonElement>("runtime-toggle");
const restartButton = element<HTMLButtonElement>("restart-button");
const applyButton = element<HTMLButtonElement>("apply-button");
const settingsActionBar = element("settings-action-bar");
const previewButton = element<HTMLButtonElement>("preview-button");
const launchAtLogin = element<HTMLInputElement>("launch-at-login");
const startMinimized = element<HTMLInputElement>("start-minimized");
const startRuntimeOnLaunch = element<HTMLInputElement>("start-runtime-on-launch");
const showFloatingIndicator = element<HTMLInputElement>("show-floating-indicator");
const activationGlowMode = element<HTMLSelectElement>("activation-glow-mode");
const scoutQueueEnabled = element<HTMLInputElement>("scout-queue-enabled");

const PERSISTED_CONTROL_IDS = [
  "voice-provider",
  "voice-locale",
  "voice-select",
  "edge-rate",
  "edge-pitch",
  "edge-volume",
  "windows-rate",
  "windows-volume",
  "assistant-name",
  "user-display-name",
  "user-first-name",
  "timezone",
  "startup-greeting",
  "updates-greeting",
  "microphone-select",
  "speech-threshold",
  "minimum-rms",
  "minimum-peak",
  "scout-queue-enabled",
  "launch-at-login",
  "start-minimized",
  "start-runtime-on-launch",
  "show-floating-indicator",
  "activation-glow-mode",
] as const;

let settings: RuntimeSettings | null = null;
let desktopPreferences: DesktopPreferences | null = null;
let appState: AppState | null = null;
let voices: VoiceOption[] = [];
let microphones: Microphone[] = [];
let busy = false;
let savedFormState: string | null = null;
let hasUnsavedChanges = false;

function signed(value: number, suffix: string): string {
  return `${value >= 0 ? "+" : ""}${String(value)}${suffix}`;
}

function numericValue(id: string): number {
  return Number(element<HTMLInputElement>(id).value);
}

function currentSettings(): RuntimeSettings {
  if (!settings) throw new Error("Arthur settings have not loaded.");
  return settings;
}

function runtimeIsRunning(): boolean {
  return appState?.runtimePid !== null && appState?.runtimePid !== undefined;
}

function notify(message: string, tone: Tone = "neutral"): void {
  operationMessage.textContent = message;
  setTone(operationMessage, tone);
}

function operationError(error: unknown): void {
  notify(error instanceof Error ? error.message : String(error), "danger");
}

function updateActionAvailability(): void {
  const ready = settings !== null && desktopPreferences !== null && appState !== null;
  runtimeToggle.disabled = busy || appState === null;
  restartButton.disabled = busy || !runtimeIsRunning();
  previewButton.disabled = busy || settings === null || voiceSelect.disabled;
  applyButton.disabled = busy || !ready || !hasUnsavedChanges;
  startMinimized.disabled = busy || !launchAtLogin.checked;
}

function setBusy(nextBusy: boolean, message?: string): void {
  busy = nextBusy;
  updateActionAvailability();
  if (message) notify(message);
}

function setOutput(id: string, value: string): void {
  const output = element<HTMLOutputElement>(id);
  output.value = value;
  output.textContent = value;
}

function updateRangeOutputs(): void {
  setOutput("edge-rate-output", signed(Number(edgeRate.value), "%"));
  setOutput("edge-pitch-output", signed(Number(edgePitch.value), "Hz"));
  setOutput("edge-volume-output", signed(Number(edgeVolume.value), "%"));
  setOutput("windows-rate-output", windowsRate.value);
  setOutput("windows-volume-output", `${windowsVolume.value}%`);
}

function updateProviderControls(): void {
  const edge = voiceProvider.value === "edge";
  edgeControls.classList.toggle("hidden", !edge);
  windowsControls.classList.toggle("hidden", edge);
}

function localeLabel(locale: string): string {
  try {
    const parsed = new Intl.Locale(locale);
    const languages = new Intl.DisplayNames([navigator.language], { type: "language" });
    const regions = new Intl.DisplayNames([navigator.language], { type: "region" });
    const language = languages.of(parsed.language) ?? parsed.language;
    const region = parsed.region ? regions.of(parsed.region) : undefined;
    return region ? `${language} (${region})` : language;
  } catch {
    return locale;
  }
}

function selectedVoiceId(): string {
  return voiceSelect.value;
}

function currentVoiceSettings(): VoiceSettings {
  const loadedSettings = currentSettings();
  const provider = voiceProvider.value === "windows" ? "windows" : "edge";
  const selectedId = selectedVoiceId();
  return {
    provider,
    edgeVoice: provider === "edge"
      ? selectedId || loadedSettings.voice.edgeVoice
      : loadedSettings.voice.edgeVoice,
    edgeRate: signed(Number(edgeRate.value), "%"),
    edgePitch: signed(Number(edgePitch.value), "Hz"),
    edgeVolume: signed(Number(edgeVolume.value), "%"),
    windowsVoiceId: provider === "windows"
      ? selectedId || loadedSettings.voice.windowsVoiceId
      : loadedSettings.voice.windowsVoiceId,
    windowsRate: Number(windowsRate.value),
    windowsVolume: Number(windowsVolume.value) / 100,
  };
}

function renderVoiceOptions(preferredId: string): void {
  const filtered = voices.filter((voice) => voice.locale === voiceLocale.value);
  if (filtered.length === 0) {
    const option = document.createElement("option");
    option.textContent = "No voices available";
    option.value = "";
    voiceSelect.replaceChildren(option);
    voiceSelect.disabled = true;
    updateActionAvailability();
    refreshUnsavedChanges();
    return;
  }

  voiceSelect.disabled = false;
  voiceSelect.replaceChildren(
    ...filtered.map((voice) => {
      const option = document.createElement("option");
      option.value = voice.id;
      option.textContent = voice.name;
      option.title = [voice.locale, voice.gender, ...voice.personalities]
        .filter(Boolean)
        .join(" · ");
      return option;
    }),
  );
  voiceSelect.value = filtered.some((voice) => voice.id === preferredId)
    ? preferredId
    : filtered[0]?.id ?? "";
  updateActionAvailability();
  refreshUnsavedChanges();
}

async function loadVoices(preferredId?: string): Promise<void> {
  const loadedSettings = currentSettings();
  const provider = voiceProvider.value === "windows" ? "windows" : "edge";
  voices = await window.arthur.listVoices(provider);
  const selectedId = preferredId
    ?? (provider === "edge"
      ? loadedSettings.voice.edgeVoice
      : loadedSettings.voice.windowsVoiceId);
  const selectedVoice = voices.find((voice) => voice.id === selectedId);
  const locales = [...new Set(voices.map((voice) => voice.locale || "Installed"))].sort();

  voiceLocale.replaceChildren(
    ...locales.map((locale) => {
      const option = document.createElement("option");
      option.value = locale;
      option.textContent = locale === "Installed" ? locale : localeLabel(locale);
      return option;
    }),
  );
  voiceLocale.value = selectedVoice?.locale
    ?? (locales.includes("en-GB") ? "en-GB" : locales[0] ?? "");
  renderVoiceOptions(selectedId);
}

function renderMicrophones(): void {
  if (microphones.length === 0) {
    const option = document.createElement("option");
    option.textContent = "No microphones found";
    option.value = "";
    microphoneSelect.replaceChildren(option);
    microphoneSelect.disabled = true;
    return;
  }

  microphoneSelect.disabled = false;
  microphoneSelect.replaceChildren(
    ...microphones.map((microphone) => {
      const option = document.createElement("option");
      option.value = microphone.id;
      option.textContent = microphone.isDefault
        ? `${microphone.name} (default)`
        : microphone.name;
      return option;
    }),
  );
  microphoneSelect.value = String(currentSettings().microphone.deviceIndex);
}

function renderSettings(nextSettings: RuntimeSettings): void {
  settings = nextSettings;
  element<HTMLInputElement>("assistant-name").value = settings.assistantName;
  element<HTMLInputElement>("user-display-name").value = settings.userDisplayName;
  element<HTMLInputElement>("user-first-name").value = settings.userFirstName;
  element<HTMLInputElement>("timezone").value = settings.timezone;
  scoutQueueEnabled.checked = settings.scoutQueueEnabled;
  element<HTMLTextAreaElement>("startup-greeting").value = settings.greetings.startup;
  element<HTMLTextAreaElement>("updates-greeting").value = settings.greetings.updates;
  element<HTMLInputElement>("speech-threshold").value = String(settings.microphone.threshold);
  element<HTMLInputElement>("minimum-rms").value = String(settings.microphone.minTranscribeRms);
  element<HTMLInputElement>("minimum-peak").value = String(settings.microphone.minTranscribePeak);
  voiceProvider.value = settings.voice.provider;
  edgeRate.value = String(Number(settings.voice.edgeRate.replace("%", "")));
  edgePitch.value = String(Number(settings.voice.edgePitch.replace("Hz", "")));
  edgeVolume.value = String(Number(settings.voice.edgeVolume.replace("%", "")));
  windowsRate.value = String(settings.voice.windowsRate);
  windowsVolume.value = String(Math.round(settings.voice.windowsVolume * 100));
  element("activation-backend").textContent = settings.speechRecognition.backend;
  element("post-activation-backend").textContent =
    settings.speechRecognition.postActivationBackend;
  element("config-path").textContent = settings.configPath;
  updateRangeOutputs();
  updateProviderControls();
  renderMicrophones();
  updateActionAvailability();
}

function renderDesktopPreferences(nextPreferences: DesktopPreferences): void {
  desktopPreferences = nextPreferences;
  launchAtLogin.checked = desktopPreferences.launchAtLogin;
  startMinimized.checked = desktopPreferences.startMinimized;
  startRuntimeOnLaunch.checked = desktopPreferences.startRuntimeOnLaunch;
  showFloatingIndicator.checked = desktopPreferences.showFloatingIndicator;
  activationGlowMode.value = desktopPreferences.showActivationHalo ? "screen" : "widget";
  updateActionAvailability();
}

function desktopPreferencesPatch(): DesktopPreferencesPatch {
  return {
    launchAtLogin: launchAtLogin.checked,
    startMinimized: startMinimized.checked,
    startRuntimeOnLaunch: startRuntimeOnLaunch.checked,
    showFloatingIndicator: showFloatingIndicator.checked,
    showActivationHalo: activationGlowMode.value === "screen",
  };
}

function settingsPatch(): RuntimeSettingsPatch {
  return {
    assistantName: element<HTMLInputElement>("assistant-name").value,
    userDisplayName: element<HTMLInputElement>("user-display-name").value,
    userFirstName: element<HTMLInputElement>("user-first-name").value,
    timezone: element<HTMLInputElement>("timezone").value,
    scoutQueueEnabled: scoutQueueEnabled.checked,
    voice: currentVoiceSettings(),
    greetings: {
      startup: element<HTMLTextAreaElement>("startup-greeting").value,
      updates: element<HTMLTextAreaElement>("updates-greeting").value,
    },
    microphone: {
      deviceIndex: Number(microphoneSelect.value),
      threshold: numericValue("speech-threshold"),
      minTranscribeRms: numericValue("minimum-rms"),
      minTranscribePeak: numericValue("minimum-peak"),
    },
  };
}

function formState(): string | null {
  if (!settings || !desktopPreferences) return null;
  return JSON.stringify({
    settings: settingsPatch(),
    desktopPreferences: desktopPreferencesPatch(),
  });
}

function setUnsavedChanges(nextValue: boolean): void {
  hasUnsavedChanges = nextValue;
  applyButton.hidden = !hasUnsavedChanges;
  settingsActionBar.dataset.dirty = String(hasUnsavedChanges);
  updateActionAvailability();
}

function refreshUnsavedChanges(): void {
  const nextFormState = formState();
  setUnsavedChanges(
    savedFormState !== null
      && nextFormState !== null
      && nextFormState !== savedFormState,
  );
}

function captureSavedFormState(): void {
  savedFormState = formState();
  setUnsavedChanges(false);
}

function renderState(nextState: AppState): void {
  appState = nextState;
  const tone: Tone = serviceStateTone(nextState.service);
  const label = serviceStateLabel(nextState.service);
  const running = runtimeIsRunning();
  const headerStatus = element("header-status");

  element("service-label").textContent = label;
  setTone(element("service-dot"), tone);
  setTone(headerStatus, tone);
  headerStatus.setAttribute("aria-label", nextState.statusMessage);
  element("recent-transcript").textContent =
    nextState.recentTranscript || nextState.statusMessage;
  element("last-command").textContent =
    nextState.lastCommandStatus || "No command available.";
  element("runtime-pid").textContent =
    nextState.runtimePid ? `PID ${String(nextState.runtimePid)}` : "Stopped";
  const runtimeLocation = element("runtime-location");
  runtimeLocation.textContent = nextState.runtimeLocation;
  runtimeLocation.title = nextState.runtimeLocation;
  element("storage-status").textContent =
    nextState.storage === "local" ? "On this device" : "External location";
  element("scout-bridge-status").textContent =
    nextState.scoutBridge === "available"
      ? "On demand"
      : nextState.scoutBridgeMessage === "Scout queueing is off"
        ? "Off"
        : "Not configured";
  element("scout-bridge-detail").textContent = nextState.scoutBridgeMessage;

  runtimeToggle.dataset.running = String(running);
  runtimeToggle.setAttribute("aria-pressed", String(running));
  setIconButton(
    runtimeToggle,
    running ? "stop" : "play",
    running ? "Stop Arthur" : "Start Arthur",
  );
  updateActionAvailability();
}

function activatePanel(panelName: PanelName): void {
  for (const name of PANEL_NAMES) {
    const selected = name === panelName;
    const tab = element<HTMLButtonElement>(`${name}-tab`);
    const panel = element(`${name}-panel`);
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    panel.hidden = !selected;
  }
}

async function applySettings(): Promise<void> {
  if (busy) return;
  const shouldRestart = runtimeIsRunning();
  const nextSettings = settingsPatch();
  const nextDesktopPreferences = desktopPreferencesPatch();
  setBusy(true, shouldRestart ? "Applying changes and restarting..." : "Applying changes...");
  try {
    renderSettings(await window.arthur.updateSettings(nextSettings));
    renderDesktopPreferences(
      await window.arthur.updateDesktopPreferences(nextDesktopPreferences),
    );
    captureSavedFormState();
    if (shouldRestart) renderState(await window.arthur.restartRuntime());
    notify(shouldRestart ? "Changes applied. Arthur restarted." : "Changes applied.", "success");
  } catch (error) {
    operationError(error);
  } finally {
    setBusy(false);
    refreshUnsavedChanges();
  }
}

async function runtimeAction(action: "toggle" | "restart"): Promise<void> {
  if (busy) return;
  const running = runtimeIsRunning();
  const message = action === "restart"
    ? "Restarting Arthur..."
    : running
      ? "Stopping Arthur..."
      : "Starting Arthur...";
  setBusy(true, message);
  try {
    const state = action === "restart"
      ? await window.arthur.restartRuntime()
      : running
        ? await window.arthur.stopRuntime()
        : await window.arthur.startRuntime();
    renderState(state);
    notify(serviceStateLabel(state.service), "success");
  } catch (error) {
    operationError(error);
  } finally {
    setBusy(false);
  }
}

async function previewVoice(): Promise<void> {
  if (busy) return;
  setBusy(true, "Playing preview...");
  try {
    await window.arthur.previewVoice({
      text: element<HTMLInputElement>("preview-text").value,
      voice: currentVoiceSettings(),
    });
    notify("Preview complete.", "success");
  } catch (error) {
    operationError(error);
  } finally {
    setBusy(false);
  }
}

async function reloadVoices(): Promise<void> {
  setBusy(true, "Loading voices...");
  try {
    updateProviderControls();
    await loadVoices();
    notify("Voice library ready.");
  } catch (error) {
    operationError(error);
  } finally {
    setBusy(false);
  }
}

async function initialize(): Promise<void> {
  setBusy(true, "Preparing local runtime...");
  try {
    const [
      initialSettings,
      initialPreferences,
      state,
      availableMicrophones,
    ] = await Promise.all([
      window.arthur.getSettings(),
      window.arthur.getDesktopPreferences(),
      window.arthur.getState(),
      window.arthur.listMicrophones(),
    ]);
    microphones = availableMicrophones;
    renderSettings(initialSettings);
    renderDesktopPreferences(initialPreferences);
    renderState(state);
    await loadVoices();
    captureSavedFormState();
    notify("Ready.");
  } catch (error) {
    operationError(error);
  } finally {
    setBusy(false);
  }
}

hydrateIcons();
activatePanel("voice");

for (const range of [edgeRate, edgePitch, edgeVolume, windowsRate, windowsVolume]) {
  range.addEventListener("input", updateRangeOutputs);
}

voiceProvider.addEventListener("change", () => {
  void reloadVoices();
});
voiceLocale.addEventListener("change", () => renderVoiceOptions(selectedVoiceId()));
previewButton.addEventListener("click", () => {
  void previewVoice();
});
applyButton.addEventListener("click", () => {
  void applySettings();
});
runtimeToggle.addEventListener("click", () => {
  void runtimeAction("toggle");
});
restartButton.addEventListener("click", () => {
  void runtimeAction("restart");
});
launchAtLogin.addEventListener("change", updateActionAvailability);
element<HTMLButtonElement>("open-logs-button").addEventListener("click", () => {
  void window.arthur.openLogs().catch(operationError);
});
element<HTMLButtonElement>("open-config-button").addEventListener("click", () => {
  void window.arthur.openConfig().catch(operationError);
});
element<HTMLButtonElement>("minimize-window").addEventListener("click", () => {
  window.arthur.minimizeWindow();
});
element<HTMLButtonElement>("close-window").addEventListener("click", () => {
  window.arthur.closeWindow();
});

for (const controlId of PERSISTED_CONTROL_IDS) {
  const control = element<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(
    controlId,
  );
  control.addEventListener("input", refreshUnsavedChanges);
  control.addEventListener("change", refreshUnsavedChanges);
}

for (const panelName of PANEL_NAMES) {
  const tab = element<HTMLButtonElement>(`${panelName}-tab`);
  tab.addEventListener("click", () => activatePanel(panelName));
  tab.addEventListener("keydown", (event) => {
    const currentIndex = PANEL_NAMES.indexOf(panelName);
    let nextIndex = currentIndex;
    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % PANEL_NAMES.length;
    if (event.key === "ArrowLeft") {
      nextIndex = (currentIndex - 1 + PANEL_NAMES.length) % PANEL_NAMES.length;
    }
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = PANEL_NAMES.length - 1;
    if (nextIndex === currentIndex) return;
    event.preventDefault();
    const nextName = PANEL_NAMES[nextIndex];
    if (!nextName) return;
    activatePanel(nextName);
    element<HTMLButtonElement>(`${nextName}-tab`).focus();
  });
}

const removeStateListener = window.arthur.onStateChanged(renderState);
window.addEventListener("beforeunload", removeStateListener, { once: true });
void initialize();
