import { spawn } from "node:child_process";

export interface ProcessResult {
  stdout: string;
  stderr: string;
}

export async function runProcess(
  executable: string,
  args: string[],
  options: {
    cwd?: string;
    timeoutMs?: number;
    env?: NodeJS.ProcessEnv;
    completion?: "close" | "exit";
  } = {},
): Promise<ProcessResult> {
  const timeoutMs = options.timeoutMs ?? 120_000;
  const completion = options.completion ?? "close";
  return await new Promise((resolve, reject) => {
    const child = spawn(executable, args, {
      cwd: options.cwd,
      windowsHide: true,
      shell: false,
      env: {
        ...process.env,
        ...options.env,
      },
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const settle = (code: number | null): void => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      if (code === 0) {
        resolve({ stdout, stderr });
      } else {
        reject(new Error(stderr.trim() || stdout.trim() || `Process exited with ${String(code)}.`));
      }
    };
    const timeout = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill();
      reject(new Error(`Process timed out after ${String(timeoutMs)}ms.`));
    }, timeoutMs);
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk: string) => {
      stderr += chunk;
    });
    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      reject(error);
    });
    child.on("exit", (code) => {
      if (completion === "exit") settle(code);
    });
    child.on("close", (code) => {
      if (completion === "close") settle(code);
    });
  });
}
