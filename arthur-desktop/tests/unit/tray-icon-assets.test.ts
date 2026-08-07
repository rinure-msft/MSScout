import assert from "node:assert/strict";
import test from "node:test";
import { tintTrayBitmap } from "../../src/main/tray-icon-assets";

void test("tray tinting preserves the executable icon alpha channel", () => {
  const source = Buffer.from([
    10, 20, 30, 0,
    80, 100, 120, 255,
  ]);
  const tinted = tintTrayBitmap(source, "listening");
  assert.equal(tinted[3], 0);
  assert.equal(tinted[7], 255);
});

void test("tray state tints produce distinct visible colours", () => {
  const source = Buffer.from([90, 110, 130, 255]);
  assert.notDeepEqual(
    tintTrayBitmap(source, "listening"),
    tintTrayBitmap(source, "error"),
  );
  assert.notDeepEqual(
    tintTrayBitmap(source, "pulse"),
    tintTrayBitmap(source, "stopped"),
  );
});
