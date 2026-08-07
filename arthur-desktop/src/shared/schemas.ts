import { z } from "zod";

const nonEmptyString = z.string().trim().min(1).max(4096);
const wakeName = z.string()
  .trim()
  .min(1)
  .max(40)
  .regex(/^[A-Za-z0-9][A-Za-z0-9' -]*$/);
const optionalVoiceId = z.string().max(4096);
const percentSetting = z.string().regex(/^[+-]\d{1,3}%$/);
const pitchSetting = z.string().regex(/^[+-]\d{1,3}Hz$/);
export const voiceProviderSchema = z.enum(["edge", "windows"]);

const widgetPositionSchema = z.object({
  x: z.number().int(),
  y: z.number().int(),
}).strict().nullable();

export const desktopPreferencesSchema = z.object({
  launchAtLogin: z.boolean(),
  startMinimized: z.boolean().default(true),
  startRuntimeOnLaunch: z.boolean(),
  showActivationHalo: z.boolean().default(false),
  showFloatingIndicator: z.boolean().default(true),
  /**
   * Nullable last-known screen position for the floating widget. Deliberately
   * absent from `desktopPreferencesPatchSchema` below: only the main process
   * writes this field (via `DesktopPreferencesStore.writePosition`) after a
   * drag, so a renderer preferences patch can never clobber it.
   */
  floatingIndicatorPosition: widgetPositionSchema.default(null),
}).strict();

export const desktopPreferencesPatchSchema = z.object({
  launchAtLogin: z.boolean().optional(),
  startMinimized: z.boolean().optional(),
  startRuntimeOnLaunch: z.boolean().optional(),
  showActivationHalo: z.boolean().optional(),
  showFloatingIndicator: z.boolean().optional(),
}).strict();

export type WidgetPosition = z.infer<typeof widgetPositionSchema>;

export const microphoneSchema = z.object({
  id: nonEmptyString,
  name: nonEmptyString,
  hostApi: z.string().max(256),
  isDefault: z.boolean(),
  channels: z.number().int().positive(),
  sampleRate: z.number().positive(),
});

export const voiceOptionSchema = z.object({
  id: nonEmptyString,
  name: nonEmptyString,
  locale: z.string().max(256),
  gender: z.string().max(64),
  provider: voiceProviderSchema,
  personalities: z.array(z.string().max(120)).max(32),
});

export const voiceSettingsSchema = z.object({
  provider: voiceProviderSchema,
  edgeVoice: nonEmptyString,
  edgeRate: percentSetting,
  edgePitch: pitchSetting,
  edgeVolume: percentSetting,
  windowsVoiceId: optionalVoiceId,
  windowsRate: z.number().int().min(50).max(400),
  windowsVolume: z.number().min(0).max(1),
});

export const runtimeSettingsSchema = z.object({
  configPath: nonEmptyString,
  assistantName: wakeName,
  userDisplayName: nonEmptyString,
  userFirstName: nonEmptyString,
  timezone: nonEmptyString,
  scoutQueueEnabled: z.boolean(),
  voice: voiceSettingsSchema,
  greetings: z.object({
    startup: z.string().min(1).max(500),
    updates: z.string().min(1).max(500),
  }),
  microphone: z.object({
    deviceIndex: z.number().int().nonnegative(),
    threshold: z.number().min(1).max(32767),
    minTranscribeRms: z.number().min(1).max(32767),
    minTranscribePeak: z.number().int().min(1).max(32767),
  }),
  speechRecognition: z.object({
    backend: z.literal("zipformer"),
    postActivationBackend: z.literal("zipformer"),
  }),
});

export const runtimeSettingsPatchSchema = z.object({
  assistantName: wakeName.optional(),
  userDisplayName: nonEmptyString.optional(),
  userFirstName: nonEmptyString.optional(),
  timezone: nonEmptyString.optional(),
  scoutQueueEnabled: z.boolean().optional(),
  voice: voiceSettingsSchema.optional(),
  greetings: runtimeSettingsSchema.shape.greetings.optional(),
  microphone: runtimeSettingsSchema.shape.microphone.optional(),
}).strict();

export const voicePreviewRequestSchema = z.object({
  text: z.string().trim().min(1).max(500),
  voice: voiceSettingsSchema,
}).strict();

export const serviceStateSchema = z.enum([
  "starting",
  "ready",
  "listening",
  "activated",
  "dictating",
  "degraded",
  "error",
  "stopped",
]);

export const appStateSchema = z.object({
  service: serviceStateSchema,
  activationId: z.string().default(""),
  statusMessage: z.string(),
  recentTranscript: z.string(),
  lastCommandStatus: z.string(),
  runtimePid: z.number().int().positive().nullable(),
  configPath: nonEmptyString,
  runtimeLocation: nonEmptyString,
  storage: z.enum(["local", "external"]),
  scoutBridge: z.enum(["available", "unavailable"]),
  scoutBridgeMessage: z.string(),
  diagnostics: z.array(z.string()),
});

export type Microphone = z.infer<typeof microphoneSchema>;
export type DesktopPreferences = z.infer<typeof desktopPreferencesSchema>;
export type DesktopPreferencesPatch = z.infer<typeof desktopPreferencesPatchSchema>;
export type VoiceOption = z.infer<typeof voiceOptionSchema>;
export type VoiceSettings = z.infer<typeof voiceSettingsSchema>;
export type RuntimeSettings = z.infer<typeof runtimeSettingsSchema>;
export type RuntimeSettingsPatch = z.infer<typeof runtimeSettingsPatchSchema>;
export type VoicePreviewRequest = z.infer<typeof voicePreviewRequestSchema>;
