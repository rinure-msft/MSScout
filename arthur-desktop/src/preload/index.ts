import { contextBridge, ipcRenderer } from "electron";
import type { ArthurApi } from "../shared/contracts";
import { IPC_CHANNELS } from "../shared/constants";
import {
  appStateSchema,
  desktopPreferencesSchema,
  microphoneSchema,
  runtimeSettingsSchema,
  voiceOptionSchema,
} from "../shared/schemas";

const api: ArthurApi = {
  getState: async () => {
    const result: unknown = await ipcRenderer.invoke(IPC_CHANNELS.getState);
    return appStateSchema.parse(result);
  },
  getSettings: async () => {
    const result: unknown = await ipcRenderer.invoke(IPC_CHANNELS.getSettings);
    return runtimeSettingsSchema.parse(result);
  },
  updateSettings: async (patch) => {
    const result: unknown = await ipcRenderer.invoke(IPC_CHANNELS.updateSettings, patch);
    return runtimeSettingsSchema.parse(result);
  },
  getDesktopPreferences: async () => {
    const result: unknown = await ipcRenderer.invoke(IPC_CHANNELS.getDesktopPreferences);
    return desktopPreferencesSchema.parse(result);
  },
  updateDesktopPreferences: async (patch) => {
    const result: unknown = await ipcRenderer.invoke(
      IPC_CHANNELS.updateDesktopPreferences,
      patch,
    );
    return desktopPreferencesSchema.parse(result);
  },
  listVoices: async (provider) => {
    const result: unknown = await ipcRenderer.invoke(IPC_CHANNELS.listVoices, provider);
    return voiceOptionSchema.array().parse(result);
  },
  listMicrophones: async () => {
    const result: unknown = await ipcRenderer.invoke(IPC_CHANNELS.listMicrophones);
    return microphoneSchema.array().parse(result);
  },
  previewVoice: async (request) => {
    await ipcRenderer.invoke(IPC_CHANNELS.previewVoice, request);
  },
  startRuntime: async () => {
    const result: unknown = await ipcRenderer.invoke(IPC_CHANNELS.startRuntime);
    return appStateSchema.parse(result);
  },
  stopRuntime: async () => {
    const result: unknown = await ipcRenderer.invoke(IPC_CHANNELS.stopRuntime);
    return appStateSchema.parse(result);
  },
  restartRuntime: async () => {
    const result: unknown = await ipcRenderer.invoke(IPC_CHANNELS.restartRuntime);
    return appStateSchema.parse(result);
  },
  openLogs: async () => {
    await ipcRenderer.invoke(IPC_CHANNELS.openLogs);
  },
  openConfig: async () => {
    await ipcRenderer.invoke(IPC_CHANNELS.openConfig);
  },
  minimizeWindow: () => ipcRenderer.send(IPC_CHANNELS.minimizeWindow),
  closeWindow: () => ipcRenderer.send(IPC_CHANNELS.closeWindow),
  showMainWindow: () => ipcRenderer.send(IPC_CHANNELS.showMainWindow),
  onStateChanged: (callback) => {
    const listener = (_event: Electron.IpcRendererEvent, state: unknown) => {
      const parsed = appStateSchema.safeParse(state);
      if (!parsed.success) {
        console.error("Arthur rejected an invalid state update.", parsed.error);
        return;
      }
      callback(parsed.data);
    };
    ipcRenderer.on(IPC_CHANNELS.stateChanged, listener);
    return () => ipcRenderer.removeListener(IPC_CHANNELS.stateChanged, listener);
  },
};

contextBridge.exposeInMainWorld("arthur", api);
