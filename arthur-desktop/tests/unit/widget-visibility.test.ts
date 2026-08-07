import assert from "node:assert/strict";
import test from "node:test";
import {
  shouldHidePopoverForMainWindow,
  shouldShowFloatingWidget,
} from "../../src/main/widget-visibility";

void test("the floating widget is shown only when enabled and the panel is hidden", () => {
  assert.equal(
    shouldShowFloatingWidget({ preferenceEnabled: true, isMainWindowVisible: false }),
    true,
  );
});

void test("showing the full panel always hides the floating widget", () => {
  assert.equal(
    shouldShowFloatingWidget({ preferenceEnabled: true, isMainWindowVisible: true }),
    false,
  );
  assert.equal(
    shouldShowFloatingWidget({ preferenceEnabled: false, isMainWindowVisible: true }),
    false,
  );
});

void test("disabling the preference keeps the widget hidden even while the panel is hidden", () => {
  assert.equal(
    shouldShowFloatingWidget({ preferenceEnabled: false, isMainWindowVisible: false }),
    false,
  );
});

void test("the popover hides whenever the full settings panel is visible", () => {
  assert.equal(shouldHidePopoverForMainWindow(true), true);
  assert.equal(shouldHidePopoverForMainWindow(false), false);
});
