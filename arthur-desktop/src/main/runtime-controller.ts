import { access, readFile } from "node:fs/promises";
import { dirname, join, resolve, sep } from "node:path";
import { shell } from "electron";
import type { AppState, ServiceState } from "../shared/contracts";
import { runProcess } from "./process-runner";

interface Heartbeat {
  status?: string;
  timestamp?: string;
  pid?: number;
  activation_id?: string;
  mic_name?: string;
  error?: string;
  message?: string;
}

interface ScoutBridgeState {
  state: "available" | "unavailable";
  message: string;
}

type JsonObject = Record<string, unknown>;

async function exists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function readJsonObject(path: string): Promise<JsonObject | null> {
  try {
    const content = (await readFile(path, "utf8")).replace(/^\uFEFF/u, "");
    const value = JSON.parse(content) as unknown;
    return typeof value === "object" && value !== null && !Array.isArray(value)
      ? value as JsonObject
      : null;
  } catch {
    return null;
  }
}

function objectValue(record: JsonObject | null, key: string): JsonObject {
  const value = record?.[key];
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as JsonObject
    : {};
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function isProcessRunning(pid: number | undefined): boolean {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function serviceState(heartbeat: Heartbeat | null, running: boolean): ServiceState {
  if (!running) return "stopped";
  const status = heartbeat?.status ?? "starting";
  if (status === "listening") return "listening";
  if (status === "activated") return "activated";
  if (status === "dictating") return "dictating";
  if (status === "paused" || status === "speaking" || status === "running") return "ready";
  if (status === "mic_timeout" || status === "failed" || status === "unhealthy") {
    return "error";
  }
  return "starting";
}

function lastMatchingValue(
  text: string,
  marker: string,
  stripBackendMetadata = false,
): string {
  const lines = text.split(/\r?\n/);
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index];
    const markerIndex = line?.indexOf(marker) ?? -1;
    if (!line || markerIndex < 0) continue;
    const value = line.slice(markerIndex + marker.length).trim();
    return stripBackendMetadata
      ? value.replace(/\s+\(backend=.*$/u, "").trim()
      : value;
  }
  return "";
}

function isPathWithin(path: string, root: string): boolean {
  const resolvedPath = resolve(path);
  const resolvedRoot = resolve(root);
  return resolvedPath.toLowerCase() === resolvedRoot.toLowerCase()
    || resolvedPath.toLowerCase().startsWith(
      `${resolvedRoot.toLowerCase()}${sep}`,
    );
}

function powershellLiteral(value: string): string {
  return `'${value.replaceAll("'", "''")}'`;
}

export class RuntimeController {
  readonly #configPath: string;
  readonly #installRoot: string;
  readonly #runtimeDir: string;
  readonly #localRuntimeRoot: string;

  public constructor(configPath: string, runtimeDir: string, localRuntimeRoot: string) {
    this.#configPath = configPath;
    this.#installRoot = dirname(configPath);
    this.#runtimeDir = runtimeDir;
    this.#localRuntimeRoot = localRuntimeRoot;
  }

  public async getState(): Promise<AppState> {
    const heartbeatPath = join(this.#installRoot, "arthur_voice_bridge_heartbeat.json");
    const heartbeat = await readJsonObject(heartbeatPath) as Heartbeat | null;
    const pid = typeof heartbeat?.pid === "number" ? heartbeat.pid : undefined;
    const running = isProcessRunning(pid);
    const transcriptLog = await this.#readText("arthur_voice_bridge_transcript.log");
    const commandLog = await this.#readText("arthur_voice_bridge_commands.log");
    const recentTranscript = lastMatchingValue(transcriptLog, "Heard: ", true);
    const lastCommandStatus = lastMatchingValue(commandLog, "Command: ");
    const service = serviceState(heartbeat, running);
    const bridge = await this.#scoutBridgeState();
    const diagnostics: string[] = [];
    if (heartbeat?.error) diagnostics.push(heartbeat.error);
    if (heartbeat?.message) diagnostics.push(heartbeat.message);
    if (heartbeat?.mic_name) diagnostics.push(`Microphone: ${heartbeat.mic_name}`);
    return {
      service,
      activationId: stringValue(heartbeat?.activation_id),
      statusMessage: running
        ? `Arthur is ${heartbeat?.status ?? "starting"}.`
        : "Arthur is stopped.",
      recentTranscript,
      lastCommandStatus,
      runtimePid: running ? pid ?? null : null,
      configPath: this.#configPath,
      runtimeLocation: this.#installRoot,
      storage: isPathWithin(this.#installRoot, this.#localRuntimeRoot)
        ? "local"
        : "external",
      scoutBridge: bridge.state,
      scoutBridgeMessage: bridge.message,
      diagnostics,
    };
  }

  public async start(): Promise<AppState> {
    const startScript = await this.#resolveRuntimeFile(
      "Start-Arthur.ps1",
      join("scripts", "Start-Arthur.ps1"),
    );
    await runProcess(
      "powershell.exe",
      ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", startScript],
      {
        cwd: this.#installRoot,
        timeoutMs: 90_000,
        env: { ARTHUR_CONFIG: this.#configPath },
        completion: "exit",
      },
    );
    return await this.getState();
  }

  public async stop(): Promise<AppState> {
    const command = [
      `$root = [System.IO.Path]::GetFullPath(${powershellLiteral(this.#installRoot)});`,
      "$patterns = @('arthur_supervisor.py','arthur_voice_bridge.py','arthur_prompt_worker.py','arthur_dashboard_server.py');",
      "$processes = Get-CimInstance Win32_Process | Where-Object {",
      "$cmd = $_.CommandLine;",
      "$_.ProcessId -ne $PID -and $_.Name -match '^python(w)?\\.exe$' -and $cmd -and",
      "$cmd.IndexOf($root, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and",
      "($patterns | Where-Object { $cmd -like \"*$_*\" })",
      "};",
      "foreach ($arthurProcess in $processes) { Stop-Process -Id $arthurProcess.ProcessId -Force -ErrorAction Stop }",
    ].join(" ");
    await runProcess(
      "powershell.exe",
      ["-NoProfile", "-Command", command],
      { timeoutMs: 30_000 },
    );
    return await this.getState();
  }

  public async restart(): Promise<AppState> {
    await this.stop();
    return await this.start();
  }

  public async openLogs(): Promise<void> {
    const result = await shell.openPath(this.#installRoot);
    if (result) throw new Error(result);
  }

  public async openConfig(): Promise<void> {
    const result = await shell.openPath(this.#configPath);
    if (result) throw new Error(result);
  }

  async #scoutBridgeState(): Promise<ScoutBridgeState> {
    const config = await readJsonObject(this.#configPath);
    const scout = objectValue(config, "scout");
    if (scout.queueEnabled !== true) {
      return {
        state: "unavailable",
        message: "Scout queueing is off",
      };
    }
    const runtime = objectValue(config, "runtime");
    const workiqPath = stringValue(runtime.workiqPath);
    const automationFile = stringValue(runtime.automationFile);
    const [handoffReady, workerReady, workiqReady, automationReady] = await Promise.all([
      exists(join(this.#installRoot, "arthur_scout_handoff.py")),
      exists(join(this.#installRoot, "arthur_prompt_worker.py")),
      workiqPath ? exists(workiqPath) : Promise.resolve(false),
      automationFile ? exists(automationFile) : Promise.resolve(false),
    ]);
    if (!handoffReady || !workerReady || (!workiqReady && !automationReady)) {
      return {
        state: "unavailable",
        message: "Independent handoff tools are not configured",
      };
    }
    if (workiqReady && automationReady) {
      return {
        state: "available",
        message: "Independent, on-demand bridge ready",
      };
    }
    return {
      state: "available",
      message: workiqReady
        ? "Independent WorkIQ bridge ready"
        : "Independent Scout handoff ready",
    };
  }

  async #resolveRuntimeFile(installedName: string, packagedRelativePath: string): Promise<string> {
    const installed = join(this.#installRoot, installedName);
    if (await exists(installed)) return installed;
    const packaged = join(this.#runtimeDir, packagedRelativePath);
    if (await exists(packaged)) return packaged;
    throw new Error(`Arthur runtime file was not found: ${installedName}`);
  }

  async #readText(name: string): Promise<string> {
    try {
      return await readFile(join(this.#installRoot, name), "utf8");
    } catch {
      return "";
    }
  }
}
