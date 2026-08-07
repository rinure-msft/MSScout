import assert from "node:assert/strict";
import test from "node:test";
import {
  desktopPreferencesPatchSchema,
  desktopPreferencesSchema,
  runtimeSettingsPatchSchema,
  voicePreviewRequestSchema,
} from "../../src/shared/schemas";

void test("voice preview rejects unsupported providers", () => {
  const result = voicePreviewRequestSchema.safeParse({
    text: "Hello",
    voice: {
      provider: "custom",
      edgeVoice: "voice",
      edgeRate: "+0%",
      edgePitch: "+0Hz",
      edgeVolume: "+0%",
      windowsVoiceId: "",
      windowsRate: 180,
      windowsVolume: 1,
    },
  });
  assert.equal(result.success, false);
});

void test("runtime settings patch rejects unknown fields", () => {
  const result = runtimeSettingsPatchSchema.safeParse({
    assistantName: "Arthur",
    arbitraryCommand: "powershell.exe",
  });
  assert.equal(result.success, false);
});

void test("runtime settings reject an unsafe wake name", () => {
  const result = runtimeSettingsPatchSchema.safeParse({
    assistantName: "Arthur.*",
  });

  assert.equal(result.success, false);
});

void test("runtime settings allow the Scout bridge to be toggled", () => {
  const result = runtimeSettingsPatchSchema.safeParse({
    scoutQueueEnabled: false,
  });
  assert.ok(result.success);
  assert.equal(result.data.scoutQueueEnabled, false);
});

void test("desktop preferences reject unknown integration settings", () => {
  const result = desktopPreferencesPatchSchema.safeParse({
    launchAtLogin: true,
    scoutSettingsPath: "C:\\private\\settings.json",
  });
  assert.equal(result.success, false);
});

void test("the activation halo preference defaults to disabled", () => {
  const preferences = desktopPreferencesSchema.parse({
    launchAtLogin: false,
    startMinimized: true,
    startRuntimeOnLaunch: false,
  });
  assert.equal(preferences.showActivationHalo, false);
});

void test("the activation halo preference can be patched independently", () => {
  const result = desktopPreferencesPatchSchema.safeParse({ showActivationHalo: true });
  assert.ok(result.success);
  assert.equal(result.data.showActivationHalo, true);
});

void test("the floating indicator preference defaults to enabled", () => {
  const preferences = desktopPreferencesSchema.parse({
    launchAtLogin: false,
    startMinimized: true,
    startRuntimeOnLaunch: false,
  });
  assert.equal(preferences.showFloatingIndicator, true);
  assert.equal(preferences.floatingIndicatorPosition, null);
});

void test("the floating indicator preference can be patched independently and kept separate from the halo", () => {
  const result = desktopPreferencesPatchSchema.safeParse({
    showFloatingIndicator: false,
    showActivationHalo: true,
  });
  assert.ok(result.success);
  assert.equal(result.data.showFloatingIndicator, false);
  assert.equal(result.data.showActivationHalo, true);
});

void test("a stored floating indicator position round-trips through the full preferences schema", () => {
  const preferences = desktopPreferencesSchema.parse({
    launchAtLogin: false,
    startMinimized: true,
    startRuntimeOnLaunch: false,
    showActivationHalo: false,
    showFloatingIndicator: true,
    floatingIndicatorPosition: { x: 12, y: 34 },
  });
  assert.deepEqual(preferences.floatingIndicatorPosition, { x: 12, y: 34 });
});

void test("the patch schema never accepts a floating indicator position", () => {
  const result = desktopPreferencesPatchSchema.safeParse({
    floatingIndicatorPosition: { x: 1, y: 2 },
  });
  assert.equal(result.success, false);
});
