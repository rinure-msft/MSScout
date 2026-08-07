import assert from "node:assert/strict";
import test from "node:test";
import {
  HEARTBEAT_FILE_NAME,
  isHeartbeatEvent,
} from "../../src/main/runtime-state-watcher";

void test("heartbeat watcher recognises only the Arthur heartbeat file", () => {
  assert.equal(isHeartbeatEvent(HEARTBEAT_FILE_NAME), true);
  assert.equal(isHeartbeatEvent(HEARTBEAT_FILE_NAME.toUpperCase()), true);
  assert.equal(isHeartbeatEvent(Buffer.from(HEARTBEAT_FILE_NAME)), true);
  assert.equal(isHeartbeatEvent("arthur_voice_bridge_stdout.log"), false);
  assert.equal(isHeartbeatEvent(null), false);
});
