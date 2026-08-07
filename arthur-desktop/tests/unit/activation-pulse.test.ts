import assert from "node:assert/strict";
import test from "node:test";
import {
  ACTIVATION_HALO_DURATION_MS,
  didActivationIdAdvance,
  didEnterActivatedState,
  shouldPulseActivationHalo,
  TRAY_PULSE_DURATION_MS,
} from "../../src/main/activation-pulse";

void test("pulse durations stay within the required 600-900ms envelope", () => {
  const trayPulseMs: number = TRAY_PULSE_DURATION_MS;
  const haloMs: number = ACTIVATION_HALO_DURATION_MS;
  assert.ok(trayPulseMs >= 600 && trayPulseMs <= 900);
  assert.ok(haloMs > 0);
});

void test("there is no pulse the first time a state is observed", () => {
  assert.equal(didEnterActivatedState(null, "activated"), false);
  assert.equal(didEnterActivatedState(null, "listening"), false);
});

void test("a pulse fires only on the transition into activated or dictating", () => {
  assert.equal(didEnterActivatedState("listening", "activated"), true);
  assert.equal(didEnterActivatedState("listening", "dictating"), true);
  assert.equal(didEnterActivatedState("ready", "listening"), false);
  assert.equal(didEnterActivatedState("activated", "dictating"), false);
  assert.equal(didEnterActivatedState("activated", "activated"), false);
});

void test("a pulse never fires on leaving the activated state", () => {
  assert.equal(didEnterActivatedState("activated", "listening"), false);
  assert.equal(didEnterActivatedState("dictating", "ready"), false);
});

void test("the activation halo only shows when both the preference and the transition agree", () => {
  assert.equal(shouldPulseActivationHalo(true, true), true);
  assert.equal(shouldPulseActivationHalo(false, true), false);
  assert.equal(shouldPulseActivationHalo(true, false), false);
  assert.equal(shouldPulseActivationHalo(false, false), false);
});

void test("a durable activation ID triggers once even when the activated state was missed", () => {
  assert.equal(didActivationIdAdvance(null, "wake-1"), false);
  assert.equal(didActivationIdAdvance("wake-1", "wake-1"), false);
  assert.equal(didActivationIdAdvance("wake-1", "wake-2"), true);
  assert.equal(didActivationIdAdvance("wake-2", ""), false);
});
