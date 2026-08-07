import assert from "node:assert/strict";
import test from "node:test";
import { runProcess } from "../../src/main/process-runner";

void test("process runner can finish when a launcher exits before inherited streams close", async () => {
  const script = [
    "const { spawn } = require('node:child_process');",
    "const child = spawn(process.execPath,",
    "  ['-e', 'setTimeout(() => process.exit(0), 1200)'],",
    "  { stdio: ['ignore', 'inherit', 'inherit'], windowsHide: true });",
    "child.unref();",
  ].join(" ");
  const startedAt = Date.now();
  await runProcess(process.execPath, ["-e", script], {
    completion: "exit",
    timeoutMs: 2_000,
  });
  assert.ok(Date.now() - startedAt < 1_000);
});
