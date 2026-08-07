import { mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { dirname } from "node:path";
import {
  runtimeSettingsPatchSchema,
  runtimeSettingsSchema,
  type RuntimeSettings,
  type RuntimeSettingsPatch,
} from "../shared/schemas";

type JsonObject = Record<string, unknown>;

function objectValue(record: JsonObject, key: string): JsonObject {
  const value = record[key];
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as JsonObject
    : {};
}

function stringValue(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function numberValue(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function booleanValue(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

export function runtimeSettingsFromConfig(raw: JsonObject, configPath: string): RuntimeSettings {
  const voice = objectValue(raw, "voice");
  const greetings = objectValue(raw, "greetings");
  const microphone = objectValue(raw, "microphone");
  const speechRecognition = objectValue(raw, "speechRecognition");
  const scout = objectValue(raw, "scout");
  return runtimeSettingsSchema.parse({
    configPath,
    assistantName: stringValue(raw.assistantName, "Arthur"),
    userDisplayName: stringValue(raw.userDisplayName, "User"),
    userFirstName: stringValue(raw.userFirstName, "User"),
    timezone: stringValue(raw.timezone, "Europe/London"),
    scoutQueueEnabled: booleanValue(scout.queueEnabled, true),
    voice: {
      provider: stringValue(voice.tts, "edge"),
      edgeVoice: stringValue(voice.edgeVoice, "en-GB-RyanNeural"),
      edgeRate: stringValue(voice.edgeRate, "+10%"),
      edgePitch: stringValue(voice.edgePitch, "+0Hz"),
      edgeVolume: stringValue(voice.edgeVolume, "+0%"),
      windowsVoiceId: typeof voice.windowsVoiceId === "string" ? voice.windowsVoiceId : "",
      windowsRate: numberValue(voice.windowsRate, 180),
      windowsVolume: numberValue(voice.windowsVolume, 1),
    },
    greetings: {
      startup: stringValue(
        greetings.startup,
        "good {time_of_day} {name}, I am ready to be of assistance.",
      ),
      updates: stringValue(
        greetings.updates,
        "good {time_of_day} {name}, your updates have been applied and I am ready to assist you.",
      ),
    },
    microphone: {
      deviceIndex: numberValue(microphone.deviceIndex, 1),
      threshold: numberValue(microphone.threshold, 350),
      minTranscribeRms: numberValue(microphone.minTranscribeRms, 120),
      minTranscribePeak: numberValue(microphone.minTranscribePeak, 700),
    },
    speechRecognition: {
      backend: stringValue(speechRecognition.backend, "zipformer"),
      postActivationBackend: stringValue(
        speechRecognition.postActivationBackend,
        "zipformer",
      ),
    },
  });
}

export function applyRuntimeSettingsPatch(
  raw: JsonObject,
  untrustedPatch: unknown,
): JsonObject {
  const patch: RuntimeSettingsPatch = runtimeSettingsPatchSchema.parse(untrustedPatch);
  const next = structuredClone(raw);
  if (patch.assistantName !== undefined) next.assistantName = patch.assistantName;
  if (patch.userDisplayName !== undefined) next.userDisplayName = patch.userDisplayName;
  if (patch.userFirstName !== undefined) next.userFirstName = patch.userFirstName;
  if (patch.timezone !== undefined) next.timezone = patch.timezone;
  if (patch.scoutQueueEnabled !== undefined) {
    next.scout = {
      ...objectValue(next, "scout"),
      queueEnabled: patch.scoutQueueEnabled,
    };
  }
  if (patch.voice !== undefined) {
    next.voice = {
      ...objectValue(next, "voice"),
      tts: patch.voice.provider,
      edgeVoice: patch.voice.edgeVoice,
      edgeRate: patch.voice.edgeRate,
      edgePitch: patch.voice.edgePitch,
      edgeVolume: patch.voice.edgeVolume,
      windowsVoiceId: patch.voice.windowsVoiceId,
      windowsRate: patch.voice.windowsRate,
      windowsVolume: patch.voice.windowsVolume,
    };
  }
  if (patch.greetings !== undefined) {
    next.greetings = {
      ...objectValue(next, "greetings"),
      ...patch.greetings,
    };
  }
  if (patch.microphone !== undefined) {
    next.microphone = {
      ...objectValue(next, "microphone"),
      ...patch.microphone,
    };
  }
  return next;
}

export class RuntimeConfigStore {
  readonly #path: string;

  public constructor(path: string) {
    this.#path = path;
  }

  public get path(): string {
    return this.#path;
  }

  public async read(): Promise<RuntimeSettings> {
    const raw = await this.#readRaw();
    return runtimeSettingsFromConfig(raw, this.#path);
  }

  public async update(patch: unknown): Promise<RuntimeSettings> {
    const raw = await this.#readRaw();
    const next = applyRuntimeSettingsPatch(raw, patch);
    await this.#writeAtomic(next);
    return runtimeSettingsFromConfig(next, this.#path);
  }

  async #readRaw(): Promise<JsonObject> {
    const content = (await readFile(this.#path, "utf8")).replace(/^\uFEFF/u, "");
    const value = JSON.parse(content) as unknown;
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      throw new Error(`Arthur config must contain a JSON object: ${this.#path}`);
    }
    return value as JsonObject;
  }

  async #writeAtomic(value: JsonObject): Promise<void> {
    await mkdir(dirname(this.#path), { recursive: true });
    const temporary = `${this.#path}.${randomUUID()}.tmp`;
    await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, {
      encoding: "utf8",
      mode: 0o600,
    });
    try {
      await rename(temporary, this.#path);
    } catch (error) {
      await rm(temporary, { force: true });
      throw error;
    }
  }
}
