import assert from "node:assert/strict";
import test from "node:test";
import {
  computePopoverPosition,
  resolveTaskbarEdge,
} from "../../src/main/popover-position";

const POPOVER_SIZE = { width: 296, height: 188 };

void test("a bottom taskbar is detected from the tray icon position", () => {
  const workArea = { x: 0, y: 0, width: 1920, height: 1040 };
  const trayBounds = { x: 1800, y: 1050, width: 16, height: 16 };
  assert.equal(resolveTaskbarEdge(trayBounds, workArea), "bottom");
});

void test("a top taskbar is detected from the tray icon position", () => {
  const workArea = { x: 0, y: 40, width: 1920, height: 1040 };
  const trayBounds = { x: 1800, y: 8, width: 16, height: 16 };
  assert.equal(resolveTaskbarEdge(trayBounds, workArea), "top");
});

void test("a left-hand taskbar is detected from the tray icon position", () => {
  const workArea = { x: 48, y: 0, width: 1872, height: 1080 };
  const trayBounds = { x: 8, y: 900, width: 16, height: 16 };
  assert.equal(resolveTaskbarEdge(trayBounds, workArea), "left");
});

void test("a right-hand taskbar is detected from the tray icon position", () => {
  const workArea = { x: 0, y: 0, width: 1872, height: 1080 };
  const trayBounds = { x: 1900, y: 900, width: 16, height: 16 };
  assert.equal(resolveTaskbarEdge(trayBounds, workArea), "right");
});

void test("the popover is anchored above the tray icon on a bottom taskbar", () => {
  const workArea = { x: 0, y: 0, width: 1920, height: 1040 };
  const trayBounds = { x: 1800, y: 1050, width: 16, height: 16 };
  const position = computePopoverPosition(trayBounds, workArea, POPOVER_SIZE);
  const expectedY = workArea.y + workArea.height - POPOVER_SIZE.height - 8;
  assert.equal(position.y, expectedY);
  assert.ok(position.y + POPOVER_SIZE.height <= trayBounds.y);
});

void test("the popover clamps to the work area instead of rendering off-screen", () => {
  const workArea = { x: 0, y: 0, width: 1920, height: 1040 };
  const trayBounds = { x: 1912, y: 1050, width: 16, height: 16 };
  const position = computePopoverPosition(trayBounds, workArea, POPOVER_SIZE);
  assert.ok(position.x >= workArea.x + 8);
  assert.ok(position.x + POPOVER_SIZE.width <= workArea.x + workArea.width - 8 + 0.001);
});

void test("the popover clamps against a work area narrower than the popover itself", () => {
  const workArea = { x: 0, y: 0, width: 200, height: 1040 };
  const trayBounds = { x: 190, y: 1050, width: 16, height: 16 };
  const position = computePopoverPosition(trayBounds, workArea, POPOVER_SIZE);
  assert.equal(Number.isFinite(position.x), true);
  assert.ok(position.x >= workArea.x);
});

void test("a left-hand taskbar anchors the popover clear of the taskbar", () => {
  const workArea = { x: 48, y: 0, width: 1872, height: 1080 };
  const trayBounds = { x: 8, y: 900, width: 16, height: 16 };
  const position = computePopoverPosition(trayBounds, workArea, POPOVER_SIZE);
  assert.equal(position.x, workArea.x + 8);
  assert.ok(position.x >= trayBounds.x + trayBounds.width);
});
