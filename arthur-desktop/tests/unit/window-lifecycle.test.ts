import assert from "node:assert/strict";
import test from "node:test";
import {
  computeCornerPosition,
  decideWindowClose,
  decideWindowMinimize,
} from "../../src/main/window-lifecycle";

void test("the main window is anchored to the bottom-right corner of the work area", () => {
  const workArea = { x: 0, y: 0, width: 1920, height: 1040 };
  const position = computeCornerPosition(workArea, { width: 404, height: 640 });
  assert.deepEqual(position, { x: 1920 - 404 - 12, y: 1040 - 640 - 12 });
});

void test("the corner margin is configurable and offsets from a non-zero work area origin", () => {
  const workArea = { x: 100, y: 40, width: 1720, height: 1000 };
  const position = computeCornerPosition(workArea, { width: 300, height: 200 }, 20);
  assert.deepEqual(position, { x: 100 + 1720 - 300 - 20, y: 40 + 1000 - 200 - 20 });
});

void test("closing the main window hides it to the tray unless the app is quitting", () => {
  assert.equal(decideWindowClose(false).shouldHide, true);
  assert.equal(decideWindowClose(true).shouldHide, false);
});

void test("minimising the main window always hides it to the background experience", () => {
  assert.equal(decideWindowMinimize().shouldHide, true);
});
