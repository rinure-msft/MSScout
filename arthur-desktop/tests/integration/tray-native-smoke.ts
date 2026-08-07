import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { app, BrowserWindow, ipcMain, screen } from "electron";
import type { AppState } from "../../src/shared/contracts";
import { IPC_CHANNELS } from "../../src/shared/constants";
import { ActivationHaloWindow } from "../../src/main/activation-halo-window";
import { FloatingWidgetWindow } from "../../src/main/floating-widget-window";
import { TrayController } from "../../src/main/tray-controller";
import { TrayPopoverWindow } from "../../src/main/tray-popover-window";
import type { Point } from "../../src/main/widget-position";

const PRIVATE_TRANSCRIPT_SENTINEL = "PRIVATE_TRANSCRIPT_MUST_NOT_RENDER";

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });
}

async function waitFor(
  predicate: () => boolean | Promise<boolean>,
  description: string,
  timeoutMs = 5_000,
): Promise<void> {
  const started = Date.now();
  while (!(await predicate())) {
    if (Date.now() - started >= timeoutMs) {
      throw new Error(`Timed out waiting for ${description}.`);
    }
    await wait(25);
  }
}

function windowForPage(pageName: string): BrowserWindow | null {
  return BrowserWindow.getAllWindows().find((window) => {
    return window.webContents.getURL().endsWith(`/${pageName}`);
  }) ?? null;
}

function state(
  service: AppState["service"],
  runtimePid: number | null,
  activationId = "",
): AppState {
  return {
    service,
    activationId,
    statusMessage: service === "stopped" ? "Arthur is stopped." : `Arthur is ${service}.`,
    recentTranscript: PRIVATE_TRANSCRIPT_SENTINEL,
    lastCommandStatus: "No action",
    runtimePid,
    configPath: "C:\\Arthur\\arthur.config.json",
    runtimeLocation: "C:\\Arthur",
    storage: "local",
    scoutBridge: "available",
    scoutBridgeMessage: "On demand",
    diagnostics: [],
  };
}

async function runSmokeTest(projectRoot: string): Promise<void> {
  const preloadPath = join(projectRoot, "dist", "preload", "index.cjs");
  const rendererRoot = join(projectRoot, "dist", "renderer");
  let currentState = state("stopped", null);
  let startCount = 0;
  let stopCount = 0;
  let showMainCount = 0;
  let persistedPosition: Point | null = null;

  ipcMain.handle(IPC_CHANNELS.getState, () => currentState);
  ipcMain.handle(IPC_CHANNELS.startRuntime, () => {
    startCount += 1;
    currentState = state("listening", 1234);
    return currentState;
  });
  ipcMain.handle(IPC_CHANNELS.stopRuntime, () => {
    stopCount += 1;
    currentState = state("stopped", null);
    return currentState;
  });
  ipcMain.on(IPC_CHANNELS.showMainWindow, () => {
    showMainCount += 1;
  });

  const popover = new TrayPopoverWindow(
    preloadPath,
    join(rendererRoot, "popover.html"),
  );
  const halo = new ActivationHaloWindow(join(rendererRoot, "halo.html"));
  const widget = new FloatingWidgetWindow(
    preloadPath,
    join(rendererRoot, "widget.html"),
    (position) => {
      persistedPosition = position;
    },
  );
  const tray = new TrayController(
    {
      onShowArthur: () => {
        showMainCount += 1;
      },
      onStartRuntime: () => {
        startCount += 1;
      },
      onStopRuntime: () => {
        stopCount += 1;
      },
      onRestartRuntime: () => undefined,
      onTogglePopover: (bounds) => {
        popover.toggle(bounds);
      },
      onQuit: () => undefined,
    },
  );

  try {
    await tray.initialize();
    assert.equal(tray.isActive(), true);
    tray.update(currentState, false);
    const trayBounds = tray.getBounds();
    assert.ok(trayBounds);

    popover.show(trayBounds);
    await waitFor(() => popover.isVisible(), "the tray popover to become visible");
    await waitFor(
      () => windowForPage("popover.html") !== null,
      "the tray popover page to load",
    );
    const popoverBrowser = windowForPage("popover.html");
    assert.ok(popoverBrowser);
    await waitFor(
      () => !popoverBrowser.webContents.isLoading(),
      "the tray popover renderer to finish loading",
    );
    const popoverText = await popoverBrowser.webContents.executeJavaScript(
      "document.body.innerText",
      true,
    ) as string;
    assert.match(popoverText, /Stopped/);
    assert.match(popoverText, /Open settings/);
    assert.doesNotMatch(popoverText, new RegExp(PRIVATE_TRANSCRIPT_SENTINEL));

    await popoverBrowser.webContents.executeJavaScript(
      "document.querySelector('#listen-toggle').click()",
      true,
    );
    await waitFor(() => startCount === 1, "the popover Listen action");

    await popoverBrowser.webContents.executeJavaScript(
      "document.querySelector('#open-settings').click()",
      true,
    );
    await waitFor(() => showMainCount === 1, "the popover Open settings action");

    popover.show(trayBounds);
    popoverBrowser.webContents.sendInputEvent({
      type: "keyDown",
      keyCode: "Escape",
    });
    await waitFor(() => !popover.isVisible(), "Escape to hide the tray popover");

    popover.toggle(trayBounds);
    await waitFor(() => popover.isVisible(), "the tray popover second toggle");
    popover.toggle(trayBounds);
    await waitFor(() => !popover.isVisible(), "the tray popover toggle to hide");

    halo.pulse(screen.getPrimaryDisplay().bounds);
    await waitFor(
      () => windowForPage("halo.html")?.isVisible() === true,
      "the activation halo to become visible",
    );
    const haloBrowser = windowForPage("halo.html");
    assert.ok(haloBrowser);
    assert.equal(haloBrowser.isFocusable(), false);
    assert.equal(haloBrowser.isAlwaysOnTop(), true);
    await waitFor(
      () => windowForPage("halo.html") === null,
      "the activation halo to dispose itself",
      3_000,
    );

    widget.show(null);
    await waitFor(() => widget.isVisible(), "the floating widget to become visible");
    await waitFor(
      () => windowForPage("widget.html") !== null,
      "the floating widget page to load",
    );
    const widgetBrowser = windowForPage("widget.html");
    assert.ok(widgetBrowser);
    await waitFor(
      () => !widgetBrowser.webContents.isLoading(),
      "the floating widget renderer to finish loading",
    );
    assert.equal(widgetBrowser.isAlwaysOnTop(), true);
    assert.equal(widgetBrowser.isResizable(), false);
    const widgetText = await widgetBrowser.webContents.executeJavaScript(
      "document.body.innerText",
      true,
    ) as string;
    assert.doesNotMatch(widgetText, new RegExp(PRIVATE_TRANSCRIPT_SENTINEL));
    assert.doesNotMatch(widgetText, /transcript/i);

    await widgetBrowser.webContents.executeJavaScript(
      "document.querySelector('#widget-listen').click()",
      true,
    );
    await waitFor(() => stopCount === 1, "clicking the widget to stop listening");

    await widgetBrowser.webContents.executeJavaScript(
      "document.querySelector('#widget-open').click()",
      true,
    );
    await waitFor(() => showMainCount === 2, "clicking the widget to open the full settings panel");
    assert.equal(popover.isVisible(), false);

    const [startX = 0, startY = 0] = widgetBrowser.getPosition();
    const draggedPosition = { x: startX + 40, y: startY + 30 };
    widgetBrowser.setPosition(draggedPosition.x, draggedPosition.y);
    await waitFor(
      () => persistedPosition !== null,
      "the dragged widget position to persist through the main-process callback",
      2_000,
    );
    assert.ok(persistedPosition);
    assert.equal((persistedPosition as Point).x, draggedPosition.x);
    assert.equal((persistedPosition as Point).y, draggedPosition.y);

    widget.broadcastState(state("dictating", 1234));
    await waitFor(
      async () => {
        const glow = await widgetBrowser.webContents.executeJavaScript(
          "document.querySelector('#widget-shell').dataset.glow",
          true,
        ) as string;
        return glow === "true";
      },
      "the widget activation bloom to start",
    );
    const toneDuringGlow = await widgetBrowser.webContents.executeJavaScript(
      "document.querySelector('#widget-shell').dataset.tone",
      true,
    ) as string;
    assert.equal(toneDuringGlow, "active");
    await waitFor(
      async () => {
        const glow = await widgetBrowser.webContents.executeJavaScript(
          "document.querySelector('#widget-shell').dataset.glow",
          true,
        ) as string;
        return glow === "false";
      },
      "the widget activation bloom to finish",
      2_000,
    );

    widget.broadcastState(state("listening", 1234, "wake-1"));
    await waitFor(
      async () => {
        const glow = await widgetBrowser.webContents.executeJavaScript(
          "document.querySelector('#widget-shell').dataset.glow",
          true,
        ) as string;
        return glow === "true";
      },
      "a durable activation ID to trigger the widget bloom",
    );
    await wait(1_000);

    currentState = state("activated", 1234);
    tray.update(currentState, true);
    await wait(900);

    process.stdout.write(`${JSON.stringify({
      status: "passed",
      popoverVisible: false,
      privateTranscriptRendered: false,
      haloDisposed: true,
      widgetPersistedPosition: persistedPosition,
      startCount,
      stopCount,
      showMainCount,
      trayBounds,
    })}\n`);
  } finally {
    widget.destroy();
    tray.destroy();
    popover.destroy();
    halo.destroy();
    ipcMain.removeHandler(IPC_CHANNELS.getState);
    ipcMain.removeHandler(IPC_CHANNELS.startRuntime);
    ipcMain.removeHandler(IPC_CHANNELS.stopRuntime);
    ipcMain.removeAllListeners(IPC_CHANNELS.showMainWindow);
  }
}

const projectRoot = process.env.ARTHUR_TRAY_SMOKE_PROJECT_ROOT;
const resultPath = process.env.ARTHUR_TRAY_SMOKE_RESULT;
if (!projectRoot) {
  throw new Error("ARTHUR_TRAY_SMOKE_PROJECT_ROOT is required.");
}
if (!resultPath) {
  throw new Error("ARTHUR_TRAY_SMOKE_RESULT is required.");
}

void app.whenReady().then(async () => {
  try {
    await runSmokeTest(projectRoot);
    await writeFile(
      resultPath,
      `${JSON.stringify({ status: "passed" })}\n`,
      "utf8",
    );
    app.exit(0);
  } catch (error) {
    console.error(error);
    await writeFile(
      resultPath,
      `${JSON.stringify({
        status: "failed",
        error: error instanceof Error ? error.stack ?? error.message : String(error),
      }, null, 2)}\n`,
      "utf8",
    );
    app.exit(1);
  }
});
