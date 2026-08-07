import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  RuntimeConfigStore,
  applyRuntimeSettingsPatch,
  runtimeSettingsFromConfig,
} from "../../src/main/runtime-config-store";

const rawConfig = {
  assistantName: "Arthur",
  userDisplayName: "Lewis Wigmore",
  userFirstName: "Lewis",
  timezone: "Europe/London",
  voice: {
    tts: "edge",
    edgeVoice: "en-GB-RyanNeural",
    edgeRate: "+0%",
    edgePitch: "+0Hz",
    edgeVolume: "+0%",
    windowsVoiceId: "",
    windowsRate: 180,
    windowsVolume: 1,
  },
  greetings: {
    startup: "Hello {name}.",
    updates: "Updates applied for {name}.",
  },
  microphone: {
    deviceIndex: 1,
    threshold: 350,
    minTranscribeRms: 120,
    minTranscribePeak: 700,
  },
  speechRecognition: {
    backend: "zipformer",
    postActivationBackend: "zipformer",
  },
  scout: {
    queueEnabled: true,
  },
  azureDevOps: {
    project: "preserve-me",
  },
};

void test("runtime settings map from the existing Arthur config", () => {
  const settings = runtimeSettingsFromConfig(rawConfig, "C:\\Arthur\\arthur.config.json");
  assert.equal(settings.voice.provider, "edge");
  assert.equal(settings.voice.edgeVoice, "en-GB-RyanNeural");
  assert.equal(settings.microphone.deviceIndex, 1);
  assert.equal(settings.speechRecognition.backend, "zipformer");
  assert.equal(settings.scoutQueueEnabled, true);
});

void test("runtime settings default to the British Ryan voice profile", () => {
  const settings = runtimeSettingsFromConfig(
    {
      ...rawConfig,
      voice: {},
    },
    "C:\\Arthur\\arthur.config.json",
  );
  assert.equal(settings.voice.edgeVoice, "en-GB-RyanNeural");
  assert.equal(settings.voice.edgeRate, "+10%");
});

void test("runtime patch preserves settings outside the desktop surface", () => {
  const updated = applyRuntimeSettingsPatch(rawConfig, {
    voice: {
      provider: "edge",
      edgeVoice: "en-GB-ThomasNeural",
      edgeRate: "-5%",
      edgePitch: "-2Hz",
      edgeVolume: "+0%",
      windowsVoiceId: "",
      windowsRate: 180,
      windowsVolume: 1,
    },
  });

  assert.deepEqual(updated.azureDevOps, rawConfig.azureDevOps);
  assert.equal((updated.voice as Record<string, unknown>).edgeVoice, "en-GB-ThomasNeural");
});

void test("runtime patch can disable Scout queueing", () => {
  const updated = applyRuntimeSettingsPatch(rawConfig, {
    scoutQueueEnabled: false,
  });
  assert.equal(
    ((updated.scout as Record<string, unknown>).queueEnabled),
    false,
  );
});

void test("runtime config store writes valid JSON atomically", async () => {
  const directory = await mkdtemp(join(tmpdir(), "arthur-desktop-test-"));
  const path = join(directory, "arthur.config.json");
  try {
    await writeFile(path, `${JSON.stringify(rawConfig, null, 2)}\n`, "utf8");
    const store = new RuntimeConfigStore(path);
    const updated = await store.update({
      assistantName: "Merlin",
      userDisplayName: "Lewis Wigmore",
      userFirstName: "Lewis",
      timezone: "Europe/London",
    });
    assert.equal(updated.assistantName, "Merlin");
    const persisted = JSON.parse(await readFile(path, "utf8")) as Record<string, unknown>;
    assert.equal(persisted.assistantName, "Merlin");
    assert.deepEqual(persisted.azureDevOps, rawConfig.azureDevOps);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

void test("runtime config store accepts UTF-8 BOM configs", async () => {
  const directory = await mkdtemp(join(tmpdir(), "arthur-desktop-test-"));
  const path = join(directory, "arthur.config.json");
  try {
    await writeFile(path, `\uFEFF${JSON.stringify(rawConfig)}\n`, "utf8");
    const settings = await new RuntimeConfigStore(path).read();
    assert.equal(settings.assistantName, "Arthur");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
