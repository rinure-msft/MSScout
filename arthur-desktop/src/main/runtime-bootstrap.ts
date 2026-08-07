import { access, readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { dirname, join } from "node:path";
import type { ArthurPaths } from "./paths";
import { runProcess } from "./process-runner";

export type RuntimePreparation =
  | { configPath: string; status: "ready" }
  | { configPath: string; status: "installed" }
  | { configPath: string; status: "updated" }
  | { configPath: string; sourceRoot: string; status: "migrated" };

export type MigrationRunner = (
  sourceRoot: string,
  destinationRoot: string,
) => Promise<void>;

export type InstallationRunner = (
  destinationRoot: string,
  pythonRoot: string,
) => Promise<void>;

export type UpdateRunner = (
  packageRoot: string,
  destinationRoot: string,
) => Promise<void>;

export interface RuntimePreparationOptions {
  installationRunner?: InstallationRunner;
  migrationRunner?: MigrationRunner;
  updateRunner?: UpdateRunner;
}

async function exists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

interface PackageIdentity {
  manifestSha256: string;
  updateComplete: boolean;
  version: string;
}

async function readPackagedIdentity(path: string): Promise<PackageIdentity | null> {
  try {
    const content = await readFile(path);
    const value = JSON.parse(content.toString("utf8")) as unknown;
    if (
      typeof value === "object"
      && value !== null
      && "packageVersion" in value
      && typeof value.packageVersion === "string"
    ) {
      return {
        manifestSha256: createHash("sha256").update(content).digest("hex").toUpperCase(),
        updateComplete: true,
        version: value.packageVersion,
      };
    }
  } catch {
    return null;
  }
  return null;
}

async function readInstalledIdentity(path: string): Promise<PackageIdentity | null> {
  try {
    const value = JSON.parse(await readFile(path, "utf8")) as unknown;
    if (
      typeof value === "object"
      && value !== null
      && "packageVersion" in value
      && typeof value.packageVersion === "string"
      && "packageManifestSha256" in value
      && typeof value.packageManifestSha256 === "string"
      && "updateStatus" in value
      && typeof value.updateStatus === "string"
    ) {
      return {
        manifestSha256: value.packageManifestSha256.toUpperCase(),
        updateComplete: value.updateStatus === "complete",
        version: value.packageVersion,
      };
    }
  } catch {
    return null;
  }
  return null;
}

async function runtimeNeedsUpdate(paths: ArthurPaths): Promise<boolean> {
  const packaged = await readPackagedIdentity(
    join(paths.runtimeDir, "arthur.package-manifest.json"),
  );
  if (!packaged) return false;
  const installed = await readInstalledIdentity(
    join(paths.localRuntimeRoot, "arthur.runtime.json"),
  );
  return installed?.version !== packaged.version
    || !installed.updateComplete
    || installed.manifestSha256 !== packaged.manifestSha256;
}

async function localRuntimeReady(paths: ArthurPaths): Promise<boolean> {
  const required = [
    paths.localConfigPath,
    paths.localPythonExecutable,
    join(paths.localRuntimeRoot, "Start-Arthur.ps1"),
    join(paths.localRuntimeRoot, "arthur_voice_bridge.py"),
    join(paths.localRuntimeRoot, "arthur_voice_catalog.py"),
    join(paths.localRuntimeRoot, "arthur.runtime.json"),
    join(
      paths.localRuntimeRoot,
      "models",
      "zipformer-en-balanced-int8",
      "encoder-epoch-99-avg-1.int8.onnx",
    ),
    join(
      paths.localRuntimeRoot,
      "models",
      "zipformer-en-balanced-int8",
      "decoder-epoch-99-avg-1.int8.onnx",
    ),
    join(
      paths.localRuntimeRoot,
      "models",
      "zipformer-en-balanced-int8",
      "joiner-epoch-99-avg-1.int8.onnx",
    ),
    join(
      paths.localRuntimeRoot,
      "models",
      "zipformer-en-balanced-int8",
      "tokens.txt",
    ),
    join(
      paths.localRuntimeRoot,
      "models",
      "zipformer-en-balanced-int8",
      "data",
      "lang_bpe_500",
      "bpe.model",
    ),
  ];
  return (await Promise.all(required.map(async (path) => await exists(path)))).every(Boolean);
}

export async function firstExistingPath(paths: string[]): Promise<string | null> {
  for (const path of paths) {
    if (await exists(path)) return path;
  }
  return null;
}

async function runMigration(
  paths: ArthurPaths,
  sourceRoot: string,
  destinationRoot: string,
): Promise<void> {
  const migrationScript = await firstExistingPath([
    join(sourceRoot, "Migrate-ArthurToLocalAppData.ps1"),
    join(paths.runtimeDir, "scripts", "Migrate-ArthurToLocalAppData.ps1"),
  ]);
  if (!migrationScript) {
    throw new Error("Arthur's local runtime migration script was not found.");
  }
  await runProcess(
    "powershell.exe",
    [
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      migrationScript,
      "-PackageRoot",
      paths.runtimeDir,
      "-SourceRoot",
      sourceRoot,
      "-DestinationRoot",
      destinationRoot,
    ],
    { timeoutMs: 15 * 60_000 },
  );
}

async function runInstallation(
  paths: ArthurPaths,
  destinationRoot: string,
  pythonRoot: string,
): Promise<void> {
  const installer = join(paths.runtimeDir, "install.ps1");
  if (!await exists(installer)) {
    throw new Error("Arthur's packaged runtime installer was not found.");
  }
  await runProcess(
    "powershell.exe",
    [
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      installer,
      "-InstallRoot",
      destinationRoot,
      "-PythonRoot",
      pythonRoot,
      "-InstallDependencies",
      "-InstallSpeechModel",
    ],
    { timeoutMs: 45 * 60_000 },
  );
}

async function runUpdate(paths: ArthurPaths): Promise<void> {
  const updater = join(paths.runtimeDir, "scripts", "Update-Arthur.ps1");
  if (!await exists(updater)) {
    throw new Error("Arthur's packaged runtime updater was not found.");
  }
  await runProcess(
    "powershell.exe",
    [
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      updater,
      "-PackageRoot",
      paths.runtimeDir,
      "-InstallRoot",
      paths.localRuntimeRoot,
      "-TrustedPackageSource",
      "-SkipRestart",
    ],
    { timeoutMs: 60 * 60_000 },
  );
}

export async function prepareLocalRuntime(
  paths: ArthurPaths,
  options: RuntimePreparationOptions = {},
): Promise<RuntimePreparation> {
  const runtimeReady = await localRuntimeReady(paths);
  if (runtimeReady && !await runtimeNeedsUpdate(paths)) {
    return { configPath: paths.localConfigPath, status: "ready" };
  }
  if (runtimeReady) {
    const update = options.updateRunner
      ?? (async () => await runUpdate(paths));
    await update(paths.runtimeDir, paths.localRuntimeRoot);
    if (!await localRuntimeReady(paths) || await runtimeNeedsUpdate(paths)) {
      throw new Error(
        `Arthur update did not create the expected runtime version: ${paths.localRuntimeRoot}`,
      );
    }
    return { configPath: paths.localConfigPath, status: "updated" };
  }

  let sourceRoot: string | null = null;
  if (!await exists(paths.localConfigPath)) {
    const legacyConfig = await firstExistingPath(paths.legacyRuntimeConfigCandidates);
    if (legacyConfig) {
      sourceRoot = dirname(legacyConfig);
      const migrate = options.migrationRunner
        ?? (async (source, destination) => await runMigration(paths, source, destination));
      await migrate(sourceRoot, paths.localRuntimeRoot);
    }
  }

  const install = options.installationRunner
    ?? (async (destination, pythonRoot) => {
      await runInstallation(paths, destination, pythonRoot);
    });
  await install(paths.localRuntimeRoot, paths.localPythonRoot);
  if (!await localRuntimeReady(paths)) {
    throw new Error(
      `Arthur installation did not create a complete local runtime: ${paths.localRuntimeRoot}`,
    );
  }
  if (!sourceRoot) {
    return {
      configPath: paths.localConfigPath,
      status: "installed",
    };
  }
  return {
    configPath: paths.localConfigPath,
    sourceRoot,
    status: "migrated",
  };
}
