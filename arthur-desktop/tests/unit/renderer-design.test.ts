import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import test from "node:test";

void test("Arthur uses an abstract vector mark instead of a letter logo", async () => {
  const html = await readFile(
    resolve("src", "renderer", "index.html"),
    "utf8",
  );
  const svg = await readFile(
    resolve("src", "renderer", "assets", "arthur-mark.svg"),
    "utf8",
  );
  const appIcon = await readFile(resolve("build", "icon.svg"), "utf8");
  const builderConfig = await readFile(
    resolve("electron-builder.yml"),
    "utf8",
  );
  assert.doesNotMatch(html, /class="brand-mark"[^>]*>\s*A\s*</i);
  assert.doesNotMatch(svg, /<text\b/i);
  assert.doesNotMatch(appIcon, /<text\b/i);
  assert.match(svg, /<path\b/i);
  assert.match(appIcon, /<path\b/i);
  assert.match(appIcon, /<linearGradient\b/i);
  assert.equal([...appIcon.matchAll(/<stop\b/gi)].length, 6);
  assert.doesNotMatch(appIcon, /<rect[^>]+width="512"[^>]+height="512"/i);
  assert.match(appIcon, /fill-rule="evenodd"/i);
  assert.doesNotMatch(appIcon, /rotate\(/i);
  assert.match(builderConfig, /icon:\s*build\/icon\.svg/);

  const pathData = (source: string): string[] =>
    [...source.matchAll(/<path\s+[^>]*d="([^"]+)"/gi)]
      .map((match) => match[1])
      .filter((value): value is string => value !== undefined);
  assert.equal(pathData(svg).length, 1);
  assert.deepEqual(pathData(appIcon), pathData(svg));
  assert.equal(appIcon, svg);
  assert.doesNotMatch(svg, /stroke-width=/);
  assert.match(svg, /feDropShadow/);
  assert.match(svg, /gradientUnits="userSpaceOnUse"/);
});

void test("compact controls share the same usable target size", async () => {
  const css = await readFile(
    resolve("src", "renderer", "styles.css"),
    "utf8",
  );
  assert.match(css, /\.icon-button[\s\S]*?width:\s*40px[\s\S]*?height:\s*40px/);
  assert.match(css, /\.button[\s\S]*?min-height:\s*40px/);
  assert.match(css, /\.brand-mark[\s\S]*?width:\s*30px[\s\S]*?height:\s*30px/);
  assert.match(css, /\.brand-mark[\s\S]*?url\("\.\/assets\/arthur-mark\.svg"\)/);
});

void test("Apply is an explicit dirty-state action", async () => {
  const html = await readFile(
    resolve("src", "renderer", "index.html"),
    "utf8",
  );
  const css = await readFile(
    resolve("src", "renderer", "styles.css"),
    "utf8",
  );
  const renderer = await readFile(
    resolve("src", "renderer", "main.ts"),
    "utf8",
  );
  const applyButton = html.match(/<button id="apply-button"[\s\S]*?<\/button>/i)?.[0];
  assert.ok(applyButton);
  assert.match(applyButton, /class="button default-button apply-action"/i);
  assert.match(applyButton, /\shidden(?:\s|>)/i);
  assert.match(applyButton, /<span>Apply changes<\/span>/i);
  assert.match(css, /\.action-bar\[data-dirty="true"\]/);
  assert.match(css, /\.apply-action\s*\{[\s\S]*?height:\s*34px/);
  assert.match(css, /\.apply-action\s*\{[\s\S]*?padding-inline:\s*12px/);
  assert.match(renderer, /function refreshUnsavedChanges\(\)/);
  assert.match(renderer, /captureSavedFormState\(\)/);
});

void test("startup options are explicit local controls", async () => {
  const html = await readFile(
    resolve("src", "renderer", "index.html"),
    "utf8",
  );
  assert.match(html, /id="launch-at-login"/);
  assert.match(html, /id="start-minimized"/);
  assert.match(html, /id="start-runtime-on-launch"/);
  assert.doesNotMatch(html, /scout-settings/i);
});

void test("the activation halo preference is an explicit opt-in local control", async () => {
  const html = await readFile(
    resolve("src", "renderer", "index.html"),
    "utf8",
  );
  const renderer = await readFile(
    resolve("src", "renderer", "main.ts"),
    "utf8",
  );
  assert.match(html, /id="activation-glow-mode"/);
  assert.match(html, />Widget only</);
  assert.match(html, />Widget \+ screen</);
  assert.match(renderer, /"activation-glow-mode"/);
  assert.match(renderer, /showActivationHalo:\s*activationGlowMode\.value === "screen"/);
});

void test("the tray popover is a compact, transcript-free surface", async () => {
  const html = await readFile(
    resolve("src", "renderer", "popover.html"),
    "utf8",
  );
  const css = await readFile(
    resolve("src", "renderer", "popover.css"),
    "utf8",
  );
  assert.match(html, /id="service-dot"/);
  assert.match(html, /id="last-action"/);
  assert.match(html, /id="listen-toggle"/);
  assert.match(html, /id="open-settings"/);
  assert.doesNotMatch(html, /recent-transcript/);
  assert.doesNotMatch(html, /recentTranscript/);
  assert.match(css, /\.popover-shell/);
});

void test("the activation halo overlay stays script-free", async () => {
  const html = await readFile(
    resolve("src", "renderer", "halo.html"),
    "utf8",
  );
  assert.match(html, /script-src 'none'/);
  assert.doesNotMatch(html, /<script/i);
});

void test("the floating widget preference is an explicit opt-out local control defaulting on", async () => {
  const html = await readFile(
    resolve("src", "renderer", "index.html"),
    "utf8",
  );
  const renderer = await readFile(
    resolve("src", "renderer", "main.ts"),
    "utf8",
  );
  assert.match(html, /id="show-floating-indicator"/);
  assert.match(html, /id="scout-queue-enabled"/);
  assert.match(html, /data-icon="plug"[\s\S]*?Scout bridge/);
  assert.match(html, /data-icon="terminal"[\s\S]*?>Runtime</);
  assert.doesNotMatch(html, /data-icon="(?:link|process)"/);
  assert.match(renderer, /"show-floating-indicator"/);
  assert.match(renderer, /showFloatingIndicator:\s*showFloatingIndicator\.checked/);
});

void test("the floating widget is a compact, transcript-free, sandboxed surface", async () => {
  const html = await readFile(
    resolve("src", "renderer", "widget.html"),
    "utf8",
  );
  const css = await readFile(
    resolve("src", "renderer", "widget.css"),
    "utf8",
  );
  const renderer = await readFile(
    resolve("src", "renderer", "widget.ts"),
    "utf8",
  );
  assert.match(html, /script-src 'self'/);
  assert.doesNotMatch(html, /recent-transcript/);
  assert.doesNotMatch(html, /recentTranscript/);
  assert.doesNotMatch(html, /transcript/i);
  assert.doesNotMatch(css, /transcript/i);
  assert.doesNotMatch(renderer, /transcriptText|recentTranscript|dictationText/i);
  assert.match(html, /id="widget-shell"/);
  assert.match(html, /id="widget-listen"/);
  assert.match(html, /id="widget-open"/);
  assert.doesNotMatch(css, /arthur-mark\.svg/);
  assert.match(html, /class="widget-grabber"/);
  assert.match(css, /width:\s*136px/);
  assert.match(css, /height:\s*72px/);
  assert.match(css, /\.widget-shell\s*\{[^}]*isolation:\s*isolate/);
  assert.match(css, /\.widget-glow\s*\{[^}]*z-index:\s*0/);
  assert.match(css, /\.widget-surface\s*\{[^}]*z-index:\s*1/);
  assert.match(css, /\.widget-state,[\s\S]*?z-index:\s*2/);
  assert.match(css, /grid-template-columns:\s*8px 10px 32px 2px 32px/);
  assert.match(css, /\.widget-state\s*\{[^}]*grid-column:\s*3/);
  assert.match(css, /\.widget-open\s*\{[^}]*grid-column:\s*5/);
  assert.match(css, /padding:\s*3px 7px 3px 11px/);
  assert.match(css, /\.widget-grabber[\s\S]*?cursor:\s*grab/);
  assert.match(css, /-webkit-app-region:\s*no-drag/);
  assert.match(css, /-webkit-app-region:\s*drag/);
  assert.match(css, /@keyframes arthur-widget-bloom/);
  assert.match(css, /900ms/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(renderer, /showMainWindow/);
  assert.doesNotMatch(renderer, /toggleWidgetPopover/);
  assert.match(renderer, /startRuntime/);
  assert.match(renderer, /stopRuntime/);
  assert.doesNotMatch(renderer, /setIconButton/);
  assert.doesNotMatch(html, /data-tooltip/);
});
