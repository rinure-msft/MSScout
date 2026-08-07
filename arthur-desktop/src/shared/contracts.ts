import type {
  DesktopPreferences,
  DesktopPreferencesPatch,
  Microphone,
  RuntimeSettings,
  RuntimeSettingsPatch,
  VoiceOption,
  VoicePreviewRequest,
} from "./schemas";

export type ServiceState =
  | "starting"
  | "ready"
  | "listening"
  | "activated"
  | "dictating"
  | "degraded"
  | "error"
  | "stopped";

export interface AppState {
  service: ServiceState;
  activationId: string;
  statusMessage: string;
  recentTranscript: string;
  lastCommandStatus: string;
  runtimePid: number | null;
  configPath: string;
  runtimeLocation: string;
  storage: "local" | "external";
  scoutBridge: "available" | "unavailable";
  scoutBridgeMessage: string;
  diagnostics: string[];
}

export interface ArthurApi {
  getState(): Promise<AppState>;
  getSettings(): Promise<RuntimeSettings>;
  updateSettings(patch: RuntimeSettingsPatch): Promise<RuntimeSettings>;
  getDesktopPreferences(): Promise<DesktopPreferences>;
  updateDesktopPreferences(
    patch: DesktopPreferencesPatch,
  ): Promise<DesktopPreferences>;
  listVoices(provider: "edge" | "windows"): Promise<VoiceOption[]>;
  listMicrophones(): Promise<Microphone[]>;
  previewVoice(request: VoicePreviewRequest): Promise<void>;
  startRuntime(): Promise<AppState>;
  stopRuntime(): Promise<AppState>;
  restartRuntime(): Promise<AppState>;
  openLogs(): Promise<void>;
  openConfig(): Promise<void>;
  minimizeWindow(): void;
  closeWindow(): void;
  showMainWindow(): void;
  onStateChanged(callback: (state: AppState) => void): () => void;
}

declare global {
  interface Window {
    arthur: ArthurApi;
  }
}
