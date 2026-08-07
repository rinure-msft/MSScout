import { watch, type FSWatcher } from "node:fs";

export const HEARTBEAT_FILE_NAME = "arthur_voice_bridge_heartbeat.json";
const DEFAULT_DEBOUNCE_MS = 40;

export function isHeartbeatEvent(filename: string | Buffer | null): boolean {
  if (filename === null) return false;
  return filename.toString().toLowerCase() === HEARTBEAT_FILE_NAME;
}

/**
 * Watches the runtime directory rather than the heartbeat file itself because
 * Arthur replaces heartbeat JSON atomically. Directory rename/change events
 * survive that replacement and are debounced into one state refresh.
 */
export class RuntimeStateWatcher {
  #watcher: FSWatcher | null = null;
  #timer: NodeJS.Timeout | null = null;
  readonly #runtimeRoot: string;
  readonly #onHeartbeat: () => void;
  readonly #onError: (error: Error) => void;
  readonly #debounceMs: number;

  public constructor(
    runtimeRoot: string,
    onHeartbeat: () => void,
    onError: (error: Error) => void,
    debounceMs = DEFAULT_DEBOUNCE_MS,
  ) {
    this.#runtimeRoot = runtimeRoot;
    this.#onHeartbeat = onHeartbeat;
    this.#onError = onError;
    this.#debounceMs = debounceMs;
  }

  public start(): void {
    if (this.#watcher) return;
    const watcher = watch(
      this.#runtimeRoot,
      { persistent: false },
      (_eventType, filename) => {
        if (!isHeartbeatEvent(filename)) return;
        if (this.#timer) clearTimeout(this.#timer);
        this.#timer = setTimeout(() => {
          this.#timer = null;
          this.#onHeartbeat();
        }, this.#debounceMs);
      },
    );
    watcher.on("error", this.#onError);
    this.#watcher = watcher;
  }

  public stop(): void {
    if (this.#timer) {
      clearTimeout(this.#timer);
      this.#timer = null;
    }
    this.#watcher?.close();
    this.#watcher = null;
  }
}
