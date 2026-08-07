import assert from "node:assert/strict";
import test from "node:test";
import type { AppState } from "../../src/shared/contracts";
import {
  buildTrayMenuTemplate,
  runtimeIsRunning,
  trayTooltipFor,
  trayVisualStateFor,
} from "../../src/main/tray-state";

function sampleState(overrides: Partial<AppState> = {}): AppState {
  return {
    service: "listening",
    activationId: "",
    statusMessage: "Arthur is listening.",
    recentTranscript: "",
    lastCommandStatus: "",
    runtimePid: 4242,
    configPath: "C:\\Arthur\\config.json",
    runtimeLocation: "C:\\Arthur\\runtime",
    storage: "local",
    scoutBridge: "unavailable",
    scoutBridgeMessage: "",
    diagnostics: [],
    ...overrides,
  };
}

void test("tray visual states reduce every service state to one of four presentations", () => {
  assert.equal(trayVisualStateFor("starting"), "stopped");
  assert.equal(trayVisualStateFor("stopped"), "stopped");
  assert.equal(trayVisualStateFor("ready"), "listening");
  assert.equal(trayVisualStateFor("listening"), "listening");
  assert.equal(trayVisualStateFor("activated"), "active");
  assert.equal(trayVisualStateFor("dictating"), "active");
  assert.equal(trayVisualStateFor("degraded"), "error");
  assert.equal(trayVisualStateFor("error"), "error");
});

void test("the tray tooltip is concise and uses a colon rather than an em dash", () => {
  const tooltip = trayTooltipFor(sampleState({ service: "listening" }));
  assert.equal(tooltip, "Arthur: Listening");
  assert.doesNotMatch(tooltip, /\u2014/);
});

void test("runtimeIsRunning reflects whether a runtime PID is present", () => {
  assert.equal(runtimeIsRunning(sampleState({ runtimePid: 99 })), true);
  assert.equal(runtimeIsRunning(sampleState({ runtimePid: null })), false);
});

void test("the tray menu offers Show Arthur, a runtime toggle, Restart and Quit", () => {
  const calls: string[] = [];
  const template = buildTrayMenuTemplate(sampleState({ runtimePid: 123 }), {
    onShowArthur: () => calls.push("show"),
    onToggleRuntime: () => calls.push("toggle"),
    onRestart: () => calls.push("restart"),
    onQuit: () => calls.push("quit"),
  });

  const labels = template.map((item) => item.label ?? "---separator---");
  assert.deepEqual(labels, [
    "Show Arthur",
    "---separator---",
    "Stop listening",
    "Restart",
    "---separator---",
    "Quit",
  ]);

  const restartItem = template.find((item) => item.label === "Restart");
  assert.equal(restartItem?.enabled, true);

  for (const item of template) item.click?.();
  assert.deepEqual(calls, ["show", "toggle", "restart", "quit"]);
});

void test("the tray menu offers to start listening and disables Restart when stopped", () => {
  const template = buildTrayMenuTemplate(sampleState({ runtimePid: null }), {
    onShowArthur: () => undefined,
    onToggleRuntime: () => undefined,
    onRestart: () => undefined,
    onQuit: () => undefined,
  });
  const toggleItem = template.find((item) => item.label === "Start listening");
  assert.ok(toggleItem);
  const restartItem = template.find((item) => item.label === "Restart");
  assert.equal(restartItem?.enabled, false);
});
