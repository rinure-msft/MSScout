import assert from "node:assert/strict";
import test from "node:test";
import {
  buildFallbackTrayBitmap,
  fallbackTrayColor,
  FALLBACK_ICON_SIZE,
} from "../../src/main/tray-icon-fallback";

void test("the fallback icon size is a small, explicit constant", () => {
  const size: number = FALLBACK_ICON_SIZE;
  assert.ok(size > 0);
  assert.ok(Number.isInteger(size));
});

void test("each tray visual state has a distinct fallback colour", () => {
  const colours = [
    fallbackTrayColor("stopped"),
    fallbackTrayColor("listening"),
    fallbackTrayColor("active"),
    fallbackTrayColor("error"),
    fallbackTrayColor("pulse"),
  ];
  const unique = new Set(colours.map((colour) => colour.join(",")));
  assert.equal(unique.size, colours.length);
});

void test("the fallback bitmap is a non-empty BGRA buffer of the requested size", () => {
  const size = 16;
  const bitmap = buildFallbackTrayBitmap("listening", size);
  assert.equal(bitmap.length, size * size * 4);
  assert.ok(bitmap.some((byte) => byte !== 0));
});

void test("the fallback bitmap encodes the state colour as BGRA at its centre pixel", () => {
  const size = 16;
  const bitmap = buildFallbackTrayBitmap("active", size);
  const [red, green, blue] = fallbackTrayColor("active");
  const center = Math.floor(size / 2);
  const offset = (center * size + center) * 4;
  assert.equal(bitmap[offset], blue);
  assert.equal(bitmap[offset + 1], green);
  assert.equal(bitmap[offset + 2], red);
  assert.equal(bitmap[offset + 3], 255);
});

void test("the fallback bitmap leaves the corners transparent, depicting a circle", () => {
  const size = 32;
  const bitmap = buildFallbackTrayBitmap("error", size);
  const cornerOffset = 0;
  assert.equal(bitmap[cornerOffset + 3], 0);
});
