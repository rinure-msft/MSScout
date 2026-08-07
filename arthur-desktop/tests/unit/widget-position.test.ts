import assert from "node:assert/strict";
import test from "node:test";
import {
  clampWidgetPosition,
  defaultWidgetPosition,
} from "../../src/main/widget-position";

const WIDGET_SIZE = { width: 136, height: 72 };

void test("the default widget position anchors to the bottom-right corner of the work area", () => {
  const workArea = { x: 0, y: 0, width: 1920, height: 1040 };
  const position = defaultWidgetPosition(workArea, WIDGET_SIZE);
  assert.deepEqual(position, { x: 1920 - 136 - 16, y: 1040 - 72 - 16 });
});

void test("the default widget margin is configurable and offsets from a non-zero work area origin", () => {
  const workArea = { x: 100, y: 40, width: 1720, height: 1000 };
  const position = defaultWidgetPosition(workArea, WIDGET_SIZE, 20);
  assert.deepEqual(position, { x: 100 + 1720 - 136 - 20, y: 40 + 1000 - 72 - 20 });
});

void test("a stored position inside the work area is left untouched", () => {
  const workArea = { x: 0, y: 0, width: 1920, height: 1040 };
  const stored = { x: 800, y: 600 };
  assert.deepEqual(clampWidgetPosition(stored, workArea, WIDGET_SIZE), stored);
});

void test("a stored position clamps back on-screen after a monitor shrinks", () => {
  const workArea = { x: 0, y: 0, width: 1280, height: 720 };
  const stored = { x: 1800, y: 1000 };
  const clamped = clampWidgetPosition(stored, workArea, WIDGET_SIZE);
  assert.ok(clamped.x + WIDGET_SIZE.width <= workArea.x + workArea.width);
  assert.ok(clamped.y + WIDGET_SIZE.height <= workArea.y + workArea.height);
  assert.ok(clamped.x >= workArea.x);
  assert.ok(clamped.y >= workArea.y);
});

void test("a stored position clamps forward on-screen after a monitor is repositioned", () => {
  const workArea = { x: 1920, y: 0, width: 1280, height: 720 };
  const stored = { x: 10, y: 10 };
  const clamped = clampWidgetPosition(stored, workArea, WIDGET_SIZE);
  assert.ok(clamped.x >= workArea.x);
  assert.ok(clamped.y >= workArea.y);
});

void test("clamping never breaks on a work area narrower than the widget itself", () => {
  const workArea = { x: 0, y: 0, width: 40, height: 1040 };
  const stored = { x: 900, y: 900 };
  const clamped = clampWidgetPosition(stored, workArea, WIDGET_SIZE);
  assert.equal(Number.isFinite(clamped.x), true);
  assert.equal(Number.isFinite(clamped.y), true);
  assert.ok(clamped.x >= workArea.x);
});

void test("a margin keeps the widget clear of the work area edge", () => {
  const workArea = { x: 0, y: 0, width: 1920, height: 1040 };
  const stored = { x: 1919, y: 1039 };
  const clamped = clampWidgetPosition(stored, workArea, WIDGET_SIZE, 8);
  assert.ok(clamped.x + WIDGET_SIZE.width <= workArea.x + workArea.width - 8 + 0.001);
  assert.ok(clamped.y + WIDGET_SIZE.height <= workArea.y + workArea.height - 8 + 0.001);
});
