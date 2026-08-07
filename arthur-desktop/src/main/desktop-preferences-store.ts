import { mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { dirname } from "node:path";
import {
  desktopPreferencesSchema,
  type DesktopPreferences,
  type WidgetPosition,
} from "../shared/schemas";

const DEFAULT_PREFERENCES: DesktopPreferences = {
  launchAtLogin: false,
  startMinimized: true,
  startRuntimeOnLaunch: false,
  showActivationHalo: false,
  showFloatingIndicator: true,
  floatingIndicatorPosition: null,
};

const CURRENT_PREFERENCE_FIELDS = [
  "startMinimized",
  "showActivationHalo",
  "showFloatingIndicator",
  "floatingIndicatorPosition",
] as const;

function isLegacyPreferences(raw: unknown): boolean {
  return typeof raw === "object"
    && raw !== null
    && !Array.isArray(raw)
    && CURRENT_PREFERENCE_FIELDS.some((field) => !Object.hasOwn(raw, field));
}

function isMissingFile(error: unknown): boolean {
  return (error as NodeJS.ErrnoException).code === "ENOENT";
}

export class DesktopPreferencesStore {
  readonly #path: string;

  public constructor(path: string) {
    this.#path = path;
  }

  public async read(): Promise<DesktopPreferences> {
    try {
      const content = (await readFile(this.#path, "utf8")).replace(/^\uFEFF/u, "");
      const raw = JSON.parse(content) as unknown;
      const preferences = desktopPreferencesSchema.parse(raw);
      if (isLegacyPreferences(raw)) {
        await this.write(preferences);
      }
      return preferences;
    } catch (error) {
      if (isMissingFile(error)) return { ...DEFAULT_PREFERENCES };
      throw error;
    }
  }

  public async write(preferences: DesktopPreferences): Promise<void> {
    const validated = desktopPreferencesSchema.parse(preferences);
    await mkdir(dirname(this.#path), { recursive: true });
    const temporary = `${this.#path}.${randomUUID()}.tmp`;
    await writeFile(temporary, `${JSON.stringify(validated, null, 2)}\n`, {
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

  /**
   * Persists only the floating widget's last-known screen position. This is
   * the sole writer of `floatingIndicatorPosition`: `desktopPreferencesPatchSchema`
   * has no such field, so a renderer preferences patch (which always
   * read-modifies-writes over the latest `read()`) can never overwrite a
   * position this method just wrote.
   */
  public async writePosition(position: WidgetPosition): Promise<DesktopPreferences> {
    const current = await this.read();
    const next: DesktopPreferences = { ...current, floatingIndicatorPosition: position };
    await this.write(next);
    return next;
  }
}
