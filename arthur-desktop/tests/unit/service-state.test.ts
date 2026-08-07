import assert from "node:assert/strict";
import test from "node:test";
import {
  isActivatedState,
  serviceStateLabel,
  serviceStateTone,
} from "../../src/shared/service-state";

void test("every service state has a concise, human-readable label", () => {
  assert.equal(serviceStateLabel("starting"), "Starting");
  assert.equal(serviceStateLabel("ready"), "Ready");
  assert.equal(serviceStateLabel("listening"), "Listening");
  assert.equal(serviceStateLabel("activated"), "Activated");
  assert.equal(serviceStateLabel("dictating"), "Dictating");
  assert.equal(serviceStateLabel("degraded"), "Needs attention");
  assert.equal(serviceStateLabel("error"), "Error");
  assert.equal(serviceStateLabel("stopped"), "Stopped");
});

void test("service state tones group states into success, warning, danger or neutral", () => {
  assert.equal(serviceStateTone("listening"), "success");
  assert.equal(serviceStateTone("ready"), "success");
  assert.equal(serviceStateTone("activated"), "success");
  assert.equal(serviceStateTone("dictating"), "success");
  assert.equal(serviceStateTone("starting"), "warning");
  assert.equal(serviceStateTone("error"), "danger");
  assert.equal(serviceStateTone("degraded"), "danger");
  assert.equal(serviceStateTone("stopped"), "neutral");
});

void test("only activated and dictating count as an active response", () => {
  assert.equal(isActivatedState("activated"), true);
  assert.equal(isActivatedState("dictating"), true);
  assert.equal(isActivatedState("listening"), false);
  assert.equal(isActivatedState("ready"), false);
  assert.equal(isActivatedState("stopped"), false);
});
