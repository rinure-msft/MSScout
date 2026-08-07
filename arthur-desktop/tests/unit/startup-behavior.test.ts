import assert from "node:assert/strict";
import test from "node:test";
import {
  HIDDEN_START_ARGUMENT,
  loginItemArguments,
  shouldStartHidden,
} from "../../src/main/startup-behavior";

void test("login startup uses a hidden argument when minimised startup is enabled", () => {
  assert.deepEqual(
    loginItemArguments({
      launchAtLogin: true,
      startMinimized: true,
      startRuntimeOnLaunch: false,
      showActivationHalo: false,
      showFloatingIndicator: true,
      floatingIndicatorPosition: null,
    }),
    [HIDDEN_START_ARGUMENT],
  );
  assert.equal(shouldStartHidden(["Arthur.exe", HIDDEN_START_ARGUMENT]), true);
});

void test("normal startup remains visible", () => {
  assert.deepEqual(
    loginItemArguments({
      launchAtLogin: true,
      startMinimized: false,
      startRuntimeOnLaunch: false,
      showActivationHalo: false,
      showFloatingIndicator: true,
      floatingIndicatorPosition: null,
    }),
    [],
  );
  assert.equal(shouldStartHidden(["Arthur.exe"]), false);
});
