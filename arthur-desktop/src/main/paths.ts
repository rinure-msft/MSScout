import { app } from "electron";
import { homedir } from "node:os";
import { join, resolve } from "node:path";

export interface ArthurPaths {
  localDataDir: string;
  localPythonExecutable: string;
  localPythonRoot: string;
  localRuntimeRoot: string;
  localConfigPath: string;
  runtimeDir: string;
  legacyRuntimeConfigCandidates: string[];
}

export function getArthurPaths(): ArthurPaths {
  const localDataDir = join(
    process.env.LOCALAPPDATA ?? app.getPath("userData"),
    "Arthur",
  );
  const localRuntimeRoot = join(localDataDir, "runtime");
  const localPythonRoot = join(localDataDir, "python");
  const localPythonExecutable = join(localPythonRoot, "python.exe");
  const localConfigPath = join(localRuntimeRoot, "arthur.config.json");
  const resources = process.resourcesPath;
  const runtimeDir = app.isPackaged
    ? join(resources, "runtime")
    : resolve(app.getAppPath(), "..", "arthur-scout");
  const home = homedir();
  const oneDrive = process.env.OneDrive;
  const legacyRuntimeConfigCandidates = [
    process.env.ARTHUR_CONFIG,
    oneDrive
      ? join(oneDrive, "Documents", "Microsoft Scout", "Scratchpad", "arthur.config.json")
      : undefined,
    join(home, "OneDrive - Microsoft", "Documents", "Microsoft Scout", "Scratchpad", "arthur.config.json"),
    join(home, "Documents", "Microsoft Scout", "Scratchpad", "arthur.config.json"),
  ]
    .filter((candidate): candidate is string => Boolean(candidate))
    .map((candidate) => resolve(candidate))
    .filter((candidate, index, candidates) => {
      return candidate !== resolve(localConfigPath) && candidates.indexOf(candidate) === index;
    });
  return {
    localDataDir,
    localPythonExecutable,
    localPythonRoot,
    localRuntimeRoot,
    localConfigPath,
    runtimeDir,
    legacyRuntimeConfigCandidates,
  };
}
