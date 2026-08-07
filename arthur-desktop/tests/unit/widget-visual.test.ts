import assert from "node:assert/strict";
import test from "node:test";
import {
  widgetRenderContractFor,
  WIDGET_GLOW_DURATION_MS,
} from "../../src/shared/widget-visual";

void test("the widget glow duration stays close to the shared 800ms activation cue", () => {
  const durationMs: number = WIDGET_GLOW_DURATION_MS;
  assert.ok(durationMs >= 600 && durationMs <= 900);
});

void test("the widget reduces every service state to one of four presentations", () => {
  assert.equal(widgetRenderContractFor(null, "starting").visualState, "stopped");
  assert.equal(widgetRenderContractFor(null, "stopped").visualState, "stopped");
  assert.equal(widgetRenderContractFor(null, "ready").visualState, "listening");
  assert.equal(widgetRenderContractFor(null, "listening").visualState, "listening");
  assert.equal(widgetRenderContractFor(null, "activated").visualState, "active");
  assert.equal(widgetRenderContractFor(null, "dictating").visualState, "active");
  assert.equal(widgetRenderContractFor(null, "degraded").visualState, "error");
  assert.equal(widgetRenderContractFor(null, "error").visualState, "error");
});

void test("there is no glow the first time a state is observed", () => {
  assert.equal(widgetRenderContractFor(null, "activated").showGlow, false);
  assert.equal(widgetRenderContractFor(null, "listening").showGlow, false);
});

void test("the glow fires only on the transition into activated or dictating", () => {
  assert.equal(widgetRenderContractFor("listening", "activated").showGlow, true);
  assert.equal(widgetRenderContractFor("listening", "dictating").showGlow, true);
  assert.equal(widgetRenderContractFor("ready", "listening").showGlow, false);
  assert.equal(widgetRenderContractFor("activated", "dictating").showGlow, false);
  assert.equal(widgetRenderContractFor("activated", "activated").showGlow, false);
});

void test("the glow never fires on leaving the activated state", () => {
  assert.equal(widgetRenderContractFor("activated", "listening").showGlow, false);
  assert.equal(widgetRenderContractFor("dictating", "ready").showGlow, false);
});

void test("the glow is a momentary cue, not a continuous animation, independent of the visual state", () => {
  const contract = widgetRenderContractFor("listening", "dictating");
  assert.equal(contract.visualState, "active");
  assert.equal(contract.showGlow, true);
});
