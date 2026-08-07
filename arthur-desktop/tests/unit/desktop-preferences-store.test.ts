import assert from "node:assert/strict";
import { mkdtemp, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { DesktopPreferencesStore } from "../../src/main/desktop-preferences-store";

void test("desktop preferences default to privacy-safe opt-in startup", async () => {
  const directory = await mkdtemp(join(tmpdir(), "arthur-preferences-"));
  try {
    const preferences = await new DesktopPreferencesStore(
      join(directory, "desktop.settings.json"),
    ).read();
    assert.deepEqual(preferences, {
      launchAtLogin: false,
      startMinimized: true,
      startRuntimeOnLaunch: false,
      showActivationHalo: false,
      showFloatingIndicator: true,
      floatingIndicatorPosition: null,
    });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

void test("desktop preferences persist locally", async () => {
  const directory = await mkdtemp(join(tmpdir(), "arthur-preferences-"));
  const path = join(directory, "desktop.settings.json");
  try {
    const store = new DesktopPreferencesStore(path);
    await store.write({
      launchAtLogin: true,
      startMinimized: false,
      startRuntimeOnLaunch: true,
      showActivationHalo: true,
      showFloatingIndicator: false,
      floatingIndicatorPosition: { x: 120, y: 240 },
    });
    assert.deepEqual(await store.read(), {
      launchAtLogin: true,
      startMinimized: false,
      startRuntimeOnLaunch: true,
      showActivationHalo: true,
      showFloatingIndicator: false,
      floatingIndicatorPosition: { x: 120, y: 240 },
    });
    const persisted = JSON.parse(await readFile(path, "utf8")) as Record<string, unknown>;
    assert.equal(persisted.launchAtLogin, true);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

void test("legacy desktop preferences default to minimised login startup", async () => {
  const directory = await mkdtemp(join(tmpdir(), "arthur-preferences-"));
  const path = join(directory, "desktop.settings.json");
  try {
    await writeFile(
      path,
      `${JSON.stringify({
        launchAtLogin: true,
        startRuntimeOnLaunch: false,
      })}\n`,
      "utf8",
    );
    assert.deepEqual(await new DesktopPreferencesStore(path).read(), {
      launchAtLogin: true,
      startMinimized: true,
      startRuntimeOnLaunch: false,
      showActivationHalo: false,
      showFloatingIndicator: true,
      floatingIndicatorPosition: null,
    });
    const migrated = JSON.parse(await readFile(path, "utf8")) as Record<string, unknown>;
    assert.equal(migrated.startMinimized, true);
    assert.equal(migrated.showActivationHalo, false);
    assert.equal(migrated.showFloatingIndicator, true);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

void test("preferences missing only the activation halo field are migrated in place", async () => {
  const directory = await mkdtemp(join(tmpdir(), "arthur-preferences-"));
  const path = join(directory, "desktop.settings.json");
  try {
    await writeFile(
      path,
      `${JSON.stringify({
        launchAtLogin: false,
        startMinimized: true,
        startRuntimeOnLaunch: false,
        showFloatingIndicator: true,
        floatingIndicatorPosition: null,
      })}\n`,
      "utf8",
    );
    assert.deepEqual(await new DesktopPreferencesStore(path).read(), {
      launchAtLogin: false,
      startMinimized: true,
      startRuntimeOnLaunch: false,
      showActivationHalo: false,
      showFloatingIndicator: true,
      floatingIndicatorPosition: null,
    });
    const migrated = JSON.parse(await readFile(path, "utf8")) as Record<string, unknown>;
    assert.equal(migrated.showActivationHalo, false);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

void test("preferences missing only the floating indicator fields are migrated atomically", async () => {
  const directory = await mkdtemp(join(tmpdir(), "arthur-preferences-"));
  const path = join(directory, "desktop.settings.json");
  try {
    await writeFile(
      path,
      `${JSON.stringify({
        launchAtLogin: false,
        startMinimized: true,
        startRuntimeOnLaunch: false,
        showActivationHalo: true,
      })}\n`,
      "utf8",
    );
    assert.deepEqual(await new DesktopPreferencesStore(path).read(), {
      launchAtLogin: false,
      startMinimized: true,
      startRuntimeOnLaunch: false,
      showActivationHalo: true,
      showFloatingIndicator: true,
      floatingIndicatorPosition: null,
    });
    const migrated = JSON.parse(await readFile(path, "utf8")) as Record<string, unknown>;
    assert.equal(migrated.showFloatingIndicator, true);
    assert.equal(migrated.floatingIndicatorPosition, null);
    const entries = await readdir(directory);
    assert.deepEqual(entries, ["desktop.settings.json"]);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

void test("writing the widget position persists it without disturbing other preferences", async () => {
  const directory = await mkdtemp(join(tmpdir(), "arthur-preferences-"));
  const path = join(directory, "desktop.settings.json");
  try {
    const store = new DesktopPreferencesStore(path);
    await store.write({
      launchAtLogin: false,
      startMinimized: true,
      startRuntimeOnLaunch: false,
      showActivationHalo: false,
      showFloatingIndicator: true,
      floatingIndicatorPosition: null,
    });
    const updated = await store.writePosition({ x: 42, y: 84 });
    assert.deepEqual(updated.floatingIndicatorPosition, { x: 42, y: 84 });
    assert.equal(updated.showFloatingIndicator, true);
    assert.deepEqual((await store.read()).floatingIndicatorPosition, { x: 42, y: 84 });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
