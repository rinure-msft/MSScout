import { dirname, join } from "node:path";
import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Menu,
  nativeTheme,
  screen,
} from "electron";
import type { AppState, ServiceState } from "../shared/contracts";
import { IPC_CHANNELS } from "../shared/constants";
import {
  desktopPreferencesPatchSchema,
  desktopPreferencesSchema,
  runtimeSettingsPatchSchema,
  type DesktopPreferences,
  voicePreviewRequestSchema,
  voiceProviderSchema,
} from "../shared/schemas";
import { ActivationHaloWindow } from "./activation-halo-window";
import {
  didActivationIdAdvance,
  didEnterActivatedState,
  shouldPulseActivationHalo,
} from "./activation-pulse";
import { DesktopPreferencesStore } from "./desktop-preferences-store";
import { FloatingWidgetWindow } from "./floating-widget-window";
import { getArthurPaths, type ArthurPaths } from "./paths";
import { RuntimeConfigStore } from "./runtime-config-store";
import {
  firstExistingPath,
  prepareLocalRuntime,
} from "./runtime-bootstrap";
import { RuntimeController } from "./runtime-controller";
import { RuntimeStateWatcher } from "./runtime-state-watcher";
import {
  loginItemArguments,
  shouldStartHidden,
} from "./startup-behavior";
import { TrayController } from "./tray-controller";
import { TrayPopoverWindow } from "./tray-popover-window";
import { VoiceService } from "./voice-service";
import type { Point } from "./widget-position";
import { shouldHidePopoverForMainWindow, shouldShowFloatingWidget } from "./widget-visibility";
import { computeCornerPosition, decideWindowClose, decideWindowMinimize } from "./window-lifecycle";

interface Services {
  configStore: RuntimeConfigStore;
  controller: RuntimeController;
  preferencesStore: DesktopPreferencesStore;
  startupError: string | null;
  voiceService: VoiceService;
}

const MAIN_WINDOW_SIZE = { width: 404, height: 640 };

let mainWindow: BrowserWindow | null = null;
let stateTimer: NodeJS.Timeout | null = null;
let trayController: TrayController | null = null;
let popoverWindow: TrayPopoverWindow | null = null;
let activationHalo: ActivationHaloWindow | null = null;
let floatingWidget: FloatingWidgetWindow | null = null;
let cachedDesktopPreferences: DesktopPreferences | null = null;
let previousServiceState: ServiceState | null = null;
let previousActivationId: string | null = null;
let runtimeStateWatcher: RuntimeStateWatcher | null = null;
let isQuitting = false;

function preloadEntryPath(): string {
  return join(__dirname, "..", "preload", "index.cjs");
}

function isMainWindowVisible(): boolean {
  return mainWindow !== null && !mainWindow.isDestroyed() && mainWindow.isVisible();
}

/**
 * Keeps the popover and the optional floating widget mutually coherent with
 * the full settings panel: showing the panel always hides both, and hiding
 * the panel shows the widget only when its preference is enabled. Called
 * from the main window's own `show`/`hide` events, so every path that shows
 * or hides the panel (Close, Minimise, a hidden startup, the tray or a
 * second launch) reaches this single decision point.
 */
function updateFloatingSurfaces(): void {
  const mainVisible = isMainWindowVisible();
  if (shouldHidePopoverForMainWindow(mainVisible)) popoverWindow?.hide();
  const showWidget = shouldShowFloatingWidget({
    preferenceEnabled: cachedDesktopPreferences?.showFloatingIndicator ?? true,
    isMainWindowVisible: mainVisible,
  });
  if (showWidget) {
    floatingWidget?.show(cachedDesktopPreferences?.floatingIndicatorPosition ?? null);
  } else {
    floatingWidget?.hide();
  }
}

function createWindow(startHidden: boolean): BrowserWindow {
  const window = new BrowserWindow({
    width: MAIN_WINDOW_SIZE.width,
    height: MAIN_WINDOW_SIZE.height,
    minWidth: 340,
    minHeight: 500,
    show: false,
    backgroundColor: nativeTheme.shouldUseDarkColors ? "#3d3b3a" : "#f7f4ef",
    title: "Arthur",
    frame: false,
    autoHideMenuBar: true,
    maximizable: false,
    webPreferences: {
      preload: preloadEntryPath(),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event) => {
    event.preventDefault();
  });
  void window.loadFile(join(__dirname, "..", "renderer", "index.html"));
  window.once("ready-to-show", () => {
    const display = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
    const [width = MAIN_WINDOW_SIZE.width, height = MAIN_WINDOW_SIZE.height] = window.getSize();
    const position = computeCornerPosition(display.workArea, { width, height });
    window.setPosition(position.x, position.y, false);
    if (!startHidden) window.show();
  });
  window.on("close", (event) => {
    if (decideWindowClose(isQuitting).shouldHide) {
      event.preventDefault();
      window.hide();
    }
  });
  window.on("minimize", () => {
    if (decideWindowMinimize().shouldHide) window.hide();
  });
  window.on("show", updateFloatingSurfaces);
  window.on("hide", updateFloatingSurfaces);
  return window;
}

/** Restores, shows and focuses the main window; used by the tray, a second launch and the popover. */
function presentMainWindow(): void {
  const window = mainWindow;
  if (!window || window.isDestroyed()) return;
  if (window.isMinimized()) window.restore();
  window.show();
  window.focus();
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function configureLoginItem(preferences: DesktopPreferences): void {
  app.setLoginItemSettings({
    openAtLogin: preferences.launchAtLogin,
    path: process.execPath,
    args: loginItemArguments(preferences),
  });
}

async function createServices(paths: ArthurPaths): Promise<Services> {
  const preparation = await prepareLocalRuntime(paths);
  const configPath = preparation.configPath;
  const configStore = new RuntimeConfigStore(configPath);
  const preferencesStore = new DesktopPreferencesStore(
    join(paths.localDataDir, "desktop.settings.json"),
  );
  const controller = new RuntimeController(
    configPath,
    paths.runtimeDir,
    paths.localRuntimeRoot,
  );
  const catalogScript = await firstExistingPath([
    join(dirname(configPath), "arthur_voice_catalog.py"),
    join(paths.runtimeDir, "src", "arthur_voice_catalog.py"),
  ]);
  if (!catalogScript) {
    throw new Error("Arthur's voice catalogue was not found.");
  }
  const voiceService = new VoiceService(
    catalogScript,
    join(dirname(configPath), "arthur_benchmark_pause.json"),
    paths.localPythonExecutable,
  );
  const preferences = await preferencesStore.read();
  cachedDesktopPreferences = preferences;
  const startupErrors: string[] = [];
  try {
    configureLoginItem(preferences);
  } catch (error) {
    startupErrors.push(`Windows startup registration failed: ${errorMessage(error)}`);
  }
  if (preferences.startRuntimeOnLaunch) {
    try {
      const state = await controller.getState();
      if (state.runtimePid === null) await controller.start();
    } catch (error) {
      startupErrors.push(`Automatic listening failed: ${errorMessage(error)}`);
    }
  }
  return {
    controller,
    configStore,
    preferencesStore,
    startupError: startupErrors.length > 0 ? startupErrors.join(" ") : null,
    voiceService,
  };
}

async function currentState(services: Services): Promise<AppState> {
  const state = await services.controller.getState();
  if (!services.startupError) return state;
  return {
    ...state,
    statusMessage: services.startupError,
    recentTranscript: services.startupError,
    diagnostics: [...state.diagnostics, services.startupError],
  };
}

function registerIpc(services: Promise<Services>): void {
  ipcMain.handle(IPC_CHANNELS.getState, async () => {
    return await currentState(await services);
  });
  ipcMain.handle(IPC_CHANNELS.getSettings, async () => {
    return await (await services).configStore.read();
  });
  ipcMain.handle(IPC_CHANNELS.updateSettings, async (_event, patch: unknown) => {
    return await (await services).configStore.update(runtimeSettingsPatchSchema.parse(patch));
  });
  ipcMain.handle(IPC_CHANNELS.getDesktopPreferences, async () => {
    return await (await services).preferencesStore.read();
  });
  ipcMain.handle(
    IPC_CHANNELS.updateDesktopPreferences,
    async (_event, patch: unknown) => {
      const service = await services;
      const current = await service.preferencesStore.read();
      const parsedPatch = desktopPreferencesPatchSchema.parse(patch);
      const next = desktopPreferencesSchema.parse({
        ...current,
        ...parsedPatch,
      });
      configureLoginItem(next);
      try {
        await service.preferencesStore.write(next);
      } catch (error) {
        configureLoginItem(current);
        throw error;
      }
      service.startupError = null;
      cachedDesktopPreferences = next;
      updateFloatingSurfaces();
      return next;
    },
  );
  ipcMain.handle(IPC_CHANNELS.listVoices, async (_event, provider: unknown) => {
    return await (await services).voiceService.listVoices(
      voiceProviderSchema.parse(provider),
    );
  });
  ipcMain.handle(IPC_CHANNELS.listMicrophones, async () => {
    return await (await services).voiceService.listMicrophones();
  });
  ipcMain.handle(IPC_CHANNELS.previewVoice, async (_event, request: unknown) => {
    await (await services).voiceService.preview(voicePreviewRequestSchema.parse(request));
  });
  ipcMain.handle(IPC_CHANNELS.startRuntime, async () => {
    const service = await services;
    const state = await service.controller.start();
    service.startupError = null;
    return state;
  });
  ipcMain.handle(IPC_CHANNELS.stopRuntime, async () => {
    const service = await services;
    const state = await service.controller.stop();
    service.startupError = null;
    return state;
  });
  ipcMain.handle(IPC_CHANNELS.restartRuntime, async () => {
    const service = await services;
    const state = await service.controller.restart();
    service.startupError = null;
    return state;
  });
  ipcMain.handle(IPC_CHANNELS.openLogs, async () => {
    await (await services).controller.openLogs();
  });
  ipcMain.handle(IPC_CHANNELS.openConfig, async () => {
    await (await services).controller.openConfig();
  });
  ipcMain.on(IPC_CHANNELS.minimizeWindow, () => {
    if (mainWindow && decideWindowMinimize().shouldHide) mainWindow.hide();
  });
  ipcMain.on(IPC_CHANNELS.closeWindow, () => mainWindow?.close());
  ipcMain.on(IPC_CHANNELS.showMainWindow, () => presentMainWindow());
}

function broadcastState(state: AppState): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(IPC_CHANNELS.stateChanged, state);
  }
}

/**
 * Single point where a freshly-fetched AppState fans out to every surface:
 * the main window, the tray icon and menu, the popover, the floating widget
 * and the optional activation halo. Keeping this in one place means there is
 * exactly one "did we just activate" check per state update, shared by the
 * tray pulse, the halo and the widget's own activation bloom.
 */
function handleStateUpdate(state: AppState): void {
  broadcastState(state);
  popoverWindow?.broadcastState(state);
  floatingWidget?.broadcastState(state);
  const enteredActivatedState = didEnterActivatedState(previousServiceState, state.service)
    || didActivationIdAdvance(previousActivationId, state.activationId);
  trayController?.update(state, enteredActivatedState);
  if (shouldPulseActivationHalo(cachedDesktopPreferences?.showActivationHalo ?? false, enteredActivatedState)) {
    const bounds = mainWindow && !mainWindow.isDestroyed() && mainWindow.isVisible()
      ? mainWindow.getBounds()
      : null;
    activationHalo?.pulse(bounds);
  }
  previousServiceState = state.service;
  previousActivationId = state.activationId;
}

async function beginStateBroadcast(services: Promise<Services>): Promise<void> {
  try {
    const service = await services;
    handleStateUpdate(await currentState(service));
    const refreshState = (): void => {
      void currentState(service)
        .then(handleStateUpdate)
        .catch((error: unknown) => {
          console.error("Arthur event-driven state refresh failed.", error);
        });
    };
    runtimeStateWatcher = new RuntimeStateWatcher(
      dirname(service.configStore.path),
      refreshState,
      (error) => {
        console.error("Arthur heartbeat watcher failed; polling remains active.", error);
      },
    );
    try {
      runtimeStateWatcher.start();
    } catch (error) {
      console.error("Arthur heartbeat watcher could not start; polling remains active.", error);
    }
    stateTimer = setInterval(() => {
      refreshState();
    }, 2_000);
  } catch (error) {
    console.error("Arthur local runtime preparation failed.", error);
  }
}

async function runTrayRuntimeAction(
  services: Promise<Services>,
  action: "start" | "stop" | "restart",
): Promise<void> {
  try {
    const service = await services;
    const state = action === "start"
      ? await service.controller.start()
      : action === "stop"
        ? await service.controller.stop()
        : await service.controller.restart();
    service.startupError = null;
    handleStateUpdate(state);
  } catch (error) {
    console.error(`Arthur tray "${action}" action failed.`, error);
  }
}

function createTrayController(services: Promise<Services>): TrayController {
  return new TrayController(
    {
      onShowArthur: presentMainWindow,
      onStartRuntime: () => {
        void runTrayRuntimeAction(services, "start");
      },
      onStopRuntime: () => {
        void runTrayRuntimeAction(services, "stop");
      },
      onRestartRuntime: () => {
        void runTrayRuntimeAction(services, "restart");
      },
      onTogglePopover: (trayBounds) => {
        popoverWindow?.toggle(trayBounds);
      },
      onQuit: () => {
        isQuitting = true;
        app.quit();
      },
    },
  );
}

async function persistWidgetPosition(
  services: Promise<Services>,
  position: Point,
): Promise<void> {
  try {
    const service = await services;
    cachedDesktopPreferences = await service.preferencesStore.writePosition(position);
  } catch (error) {
    console.error("Arthur could not persist the floating widget position.", error);
  }
}

function startApplication(): void {
  nativeTheme.themeSource = "system";
  Menu.setApplicationMenu(null);
  const services = createServices(getArthurPaths());
  registerIpc(services);
  mainWindow = createWindow(shouldStartHidden(process.argv));
  popoverWindow = new TrayPopoverWindow(
    preloadEntryPath(),
    join(__dirname, "..", "renderer", "popover.html"),
  );
  activationHalo = new ActivationHaloWindow(join(__dirname, "..", "renderer", "halo.html"));
  floatingWidget = new FloatingWidgetWindow(
    preloadEntryPath(),
    join(__dirname, "..", "renderer", "widget.html"),
    (position) => {
      void persistWidgetPosition(services, position);
    },
  );
  trayController = createTrayController(services);
  void trayController.initialize().then(() => {
    void beginStateBroadcast(services);
  }).catch((error: unknown) => {
    console.error("Arthur tray failed to initialise.", error);
    void beginStateBroadcast(services);
  });
  // The main window may never show (a `--hidden` startup), so `show`/`hide`
  // events alone would never reveal the widget; run the decision once more
  // as soon as the real preferences are loaded.
  void services.then(() => {
    updateFloatingSurfaces();
  }).catch(() => undefined);
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

const hasLock = app.requestSingleInstanceLock();
if (!hasLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    presentMainWindow();
  });
  app.whenReady().then(startApplication).catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    dialog.showErrorBox("Arthur failed to start", message);
    app.quit();
  });
}

app.on("window-all-closed", () => {
  // The main window hides to the tray instead of quitting the app. Only
  // fall back to quitting if the tray genuinely never became available.
  if (!trayController?.isActive()) app.quit();
});

app.on("before-quit", () => {
  isQuitting = true;
  if (stateTimer) clearInterval(stateTimer);
  runtimeStateWatcher?.stop();
  trayController?.destroy();
  popoverWindow?.destroy();
  activationHalo?.destroy();
  floatingWidget?.destroy();
});
