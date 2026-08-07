import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import type { ArthurPaths } from "../../src/main/paths";
import { prepareLocalRuntime } from "../../src/main/runtime-bootstrap";

function paths(root: string): ArthurPaths {
  const localRuntimeRoot = join(root, "local", "runtime");
  return {
    localConfigPath: join(localRuntimeRoot, "arthur.config.json"),
    localDataDir: join(root, "local"),
    localPythonExecutable: join(root, "local", "python", "python.exe"),
    localPythonRoot: join(root, "local", "python"),
    localRuntimeRoot,
    runtimeDir: join(root, "package"),
    legacyRuntimeConfigCandidates: [
      join(root, "legacy", "arthur.config.json"),
    ],
  };
}

async function writeLocalRuntime(runtimePaths: ArthurPaths): Promise<void> {
  await mkdir(runtimePaths.localRuntimeRoot, { recursive: true });
  await mkdir(runtimePaths.localPythonRoot, { recursive: true });
  const modelRoot = join(
    runtimePaths.localRuntimeRoot,
    "models",
    "zipformer-en-balanced-int8",
  );
  await mkdir(join(modelRoot, "data", "lang_bpe_500"), { recursive: true });
  await Promise.all([
    writeFile(runtimePaths.localConfigPath, "{}\n", "utf8"),
    writeFile(runtimePaths.localPythonExecutable, "", "utf8"),
    writeFile(join(runtimePaths.localRuntimeRoot, "Start-Arthur.ps1"), "", "utf8"),
    writeFile(join(runtimePaths.localRuntimeRoot, "arthur_voice_bridge.py"), "", "utf8"),
    writeFile(join(runtimePaths.localRuntimeRoot, "arthur_voice_catalog.py"), "", "utf8"),
    writeFile(join(runtimePaths.localRuntimeRoot, "arthur.runtime.json"), "{}\n", "utf8"),
    writeFile(join(modelRoot, "encoder-epoch-99-avg-1.int8.onnx"), "", "utf8"),
    writeFile(join(modelRoot, "decoder-epoch-99-avg-1.int8.onnx"), "", "utf8"),
    writeFile(join(modelRoot, "joiner-epoch-99-avg-1.int8.onnx"), "", "utf8"),
    writeFile(join(modelRoot, "tokens.txt"), "", "utf8"),
    writeFile(join(modelRoot, "data", "lang_bpe_500", "bpe.model"), "", "utf8"),
  ]);
}

void test("local runtime is used without migration", async () => {
  const root = await mkdtemp(join(tmpdir(), "arthur-bootstrap-"));
  const runtimePaths = paths(root);
  try {
    await writeLocalRuntime(runtimePaths);
    let migrated = false;
    const result = await prepareLocalRuntime(runtimePaths, {
      installationRunner: () => {
        throw new Error("Installation should not run.");
      },
      migrationRunner: () => {
        migrated = true;
        return Promise.resolve();
      },
    });
    assert.equal(result.status, "ready");
    assert.equal(result.configPath, runtimePaths.localConfigPath);
    assert.equal(migrated, false);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

void test("legacy runtime is copied to LocalAppData once", async () => {
  const root = await mkdtemp(join(tmpdir(), "arthur-bootstrap-"));
  const runtimePaths = paths(root);
  const legacyConfig = runtimePaths.legacyRuntimeConfigCandidates[0];
  if (!legacyConfig) throw new Error("Missing legacy test config path.");
  try {
    await mkdir(join(root, "legacy"), { recursive: true });
    await writeFile(legacyConfig, "{}\n", "utf8");
    let installed = false;
    const result = await prepareLocalRuntime(runtimePaths, {
      migrationRunner: async (sourceRoot, destinationRoot) => {
        assert.equal(sourceRoot, join(root, "legacy"));
        assert.equal(destinationRoot, runtimePaths.localRuntimeRoot);
        await mkdir(destinationRoot, { recursive: true });
        await writeFile(runtimePaths.localConfigPath, "{}\n", "utf8");
      },
      installationRunner: async (destinationRoot, pythonRoot) => {
        assert.equal(destinationRoot, runtimePaths.localRuntimeRoot);
        assert.equal(pythonRoot, runtimePaths.localPythonRoot);
        installed = true;
        await writeLocalRuntime(runtimePaths);
      },
    });
    assert.equal(result.status, "migrated");
    assert.equal(result.configPath, runtimePaths.localConfigPath);
    assert.equal(installed, true);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

void test("missing local and legacy runtimes install from the package", async () => {
  const root = await mkdtemp(join(tmpdir(), "arthur-bootstrap-"));
  const runtimePaths = paths(root);
  try {
    let migrated = false;
    const result = await prepareLocalRuntime(runtimePaths, {
      migrationRunner: () => {
        migrated = true;
        return Promise.resolve();
      },
      installationRunner: async (destinationRoot, pythonRoot) => {
        assert.equal(destinationRoot, runtimePaths.localRuntimeRoot);
        assert.equal(pythonRoot, runtimePaths.localPythonRoot);
        await writeLocalRuntime(runtimePaths);
      },
    });
    assert.equal(result.status, "installed");
    assert.equal(result.configPath, runtimePaths.localConfigPath);
    assert.equal(migrated, false);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

void test("incomplete local runtime is repaired without legacy migration", async () => {
  const root = await mkdtemp(join(tmpdir(), "arthur-bootstrap-"));
  const runtimePaths = paths(root);
  try {
    await mkdir(runtimePaths.localRuntimeRoot, { recursive: true });
    await writeFile(runtimePaths.localConfigPath, "{}\n", "utf8");
    let migrated = false;
    const result = await prepareLocalRuntime(runtimePaths, {
      migrationRunner: () => {
        migrated = true;
        return Promise.resolve();
      },
      installationRunner: async () => {
        await writeLocalRuntime(runtimePaths);
      },
    });
    assert.equal(result.status, "installed");
    assert.equal(migrated, false);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

void test("an older complete runtime is transactionally updated from the package", async () => {
  const root = await mkdtemp(join(tmpdir(), "arthur-bootstrap-"));
  const runtimePaths = paths(root);
  try {
    await writeLocalRuntime(runtimePaths);
    await writeFile(
      join(runtimePaths.localRuntimeRoot, "arthur.runtime.json"),
      JSON.stringify({ packageVersion: "0.3.0" }),
      "utf8",
    );
    await mkdir(runtimePaths.runtimeDir, { recursive: true });
    const packageManifestPath = join(
      runtimePaths.runtimeDir,
      "arthur.package-manifest.json",
    );
    await writeFile(packageManifestPath, JSON.stringify({ packageVersion: "0.4.0" }), "utf8");
    const packageManifestSha256 = createHash("sha256")
      .update(await readFile(packageManifestPath))
      .digest("hex")
      .toUpperCase();
    let updated = false;
    const result = await prepareLocalRuntime(runtimePaths, {
      updateRunner: async (packageRoot, destinationRoot) => {
        assert.equal(packageRoot, runtimePaths.runtimeDir);
        assert.equal(destinationRoot, runtimePaths.localRuntimeRoot);
        updated = true;
        await writeFile(
          join(runtimePaths.localRuntimeRoot, "arthur.runtime.json"),
          JSON.stringify({
            packageManifestSha256,
            packageVersion: "0.4.0",
            updateStatus: "complete",
          }),
          "utf8",
        );
      },
      installationRunner: () => {
        throw new Error("Installation should not run for an upgrade.");
      },
    });
    assert.equal(result.status, "updated");
    assert.equal(updated, true);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
