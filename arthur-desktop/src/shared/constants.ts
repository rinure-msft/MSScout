export const APP_NAME = "Arthur";

export const IPC_CHANNELS = {
  getState: "arthur:state:get",
  getSettings: "arthur:runtime-settings:get",
  updateSettings: "arthur:runtime-settings:update",
  getDesktopPreferences: "arthur:desktop-preferences:get",
  updateDesktopPreferences: "arthur:desktop-preferences:update",
  listVoices: "arthur:voices:list",
  listMicrophones: "arthur:microphones:list",
  previewVoice: "arthur:voice:preview",
  startRuntime: "arthur:runtime:start",
  stopRuntime: "arthur:runtime:stop",
  restartRuntime: "arthur:runtime:restart",
  openLogs: "arthur:logs:open",
  openConfig: "arthur:config:open",
  minimizeWindow: "arthur:window:minimize",
  closeWindow: "arthur:window:close",
  showMainWindow: "arthur:window:show-main",
  stateChanged: "arthur:state:changed",
} as const;
