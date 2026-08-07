import { microphoneSchema, voiceOptionSchema, voicePreviewRequestSchema } from "../shared/schemas";
import type { Microphone, VoiceOption } from "../shared/schemas";
import { runProcess } from "./process-runner";
import { access, rm, writeFile } from "node:fs/promises";

function parseLastJsonLine(output: string): unknown {
  const lines = output.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const last = lines.at(-1);
  if (!last) throw new Error("Arthur voice command returned no JSON.");
  return JSON.parse(last) as unknown;
}

export class VoiceService {
  readonly #python: string;
  readonly #catalogScript: string;
  readonly #pauseFile: string;

  public constructor(
    catalogScript: string,
    pauseFile: string,
    python = process.env.ARTHUR_PYTHON ?? "python",
  ) {
    this.#catalogScript = catalogScript;
    this.#pauseFile = pauseFile;
    this.#python = python;
  }

  public async listVoices(provider: "edge" | "windows"): Promise<VoiceOption[]> {
    const result = await runProcess(
      this.#python,
      ["-s", this.#catalogScript, "--list", provider],
      { env: { PYGAME_HIDE_SUPPORT_PROMPT: "1", PYTHONNOUSERSITE: "1" } },
    );
    return voiceOptionSchema.array().parse(parseLastJsonLine(result.stdout));
  }

  public async listMicrophones(): Promise<Microphone[]> {
    const result = await runProcess(
      this.#python,
      ["-s", this.#catalogScript, "--list", "microphones"],
      { env: { PYGAME_HIDE_SUPPORT_PROMPT: "1", PYTHONNOUSERSITE: "1" } },
    );
    return microphoneSchema.array().parse(parseLastJsonLine(result.stdout));
  }

  public async preview(untrustedRequest: unknown): Promise<void> {
    const request = voicePreviewRequestSchema.parse(untrustedRequest);
    const voice = request.voice;
    const args = [
      "-s",
      this.#catalogScript,
      "--preview",
      voice.provider,
      "--text",
      request.text,
      "--voice",
      voice.provider === "edge" ? voice.edgeVoice : voice.windowsVoiceId,
      "--rate",
      voice.edgeRate,
      "--pitch",
      voice.edgePitch,
      "--volume",
      voice.edgeVolume,
      "--windows-rate",
      String(voice.windowsRate),
      "--windows-volume",
      String(voice.windowsVolume),
    ];
    let pauseAlreadyPresent = false;
    try {
      await access(this.#pauseFile);
      pauseAlreadyPresent = true;
    } catch {
      await writeFile(
        this.#pauseFile,
        `${JSON.stringify({ reason: "voice preview", ownerPid: process.pid })}\n`,
        "utf8",
      );
    }
    try {
      await runProcess(this.#python, args, {
        env: { PYGAME_HIDE_SUPPORT_PROMPT: "1", PYTHONNOUSERSITE: "1" },
      });
    } finally {
      if (!pauseAlreadyPresent) {
        await rm(this.#pauseFile, { force: true });
      }
    }
  }
}
