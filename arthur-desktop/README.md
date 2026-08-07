# Arthur Desktop

Arthur Desktop is a compact local control panel for the Python voice runtime. Voice
capture, models, queues, logs and configuration run from
`%LOCALAPPDATA%\Arthur\runtime`.

On first launch, Arthur repairs or creates its LocalAppData runtime directly
from the packaged sidecar. If an older Scout Scratchpad runtime exists, its
configuration and model can be migrated once before the private runtime is
provisioned. The source is preserved until the verified legacy cleanup is run,
but all new Arthur state is written locally.

## Product principles

- Local-first storage for operational data and speech models.
- A small bottom-right window with no application menu.
- One abstract vector mark, compact typography and a single accent colour.
- Reusable 40 pixel icon controls with accessible names and keyboard focus.
- One settings view at a time, with no hidden horizontal overflow.
- Explicit Scout handoff only. Scheduled Scout automations remain disabled.

## Capabilities

- Start, stop and restart the local Arthur runtime.
- Read live status and the latest speech transcript.
- Select Edge neural or installed Windows voices.
- Adjust rate, pitch and volume.
- Preview voices while Arthur command routing is paused.
- Select the microphone and tune advanced detection settings.
- Personalise names, timezone and greetings.
- Optionally launch Arthur at Windows sign-in.
- Optionally start hidden at sign-in while normal launches remain visible.
- Optionally start the local listener when the desktop app opens.
- Open the local config and runtime folder.
- Report whether the on-demand Scout bridge is available.
- Live in the Windows notification area with a state-aware tray icon.
- Toggle a compact tray popover for status and a quick Listen or Pause control.
- Optionally show a small floating indicator while Arthur is minimised.
- Optionally show a brief on-screen halo when Arthur activates.

## Tray and popover

Arthur keeps a permanent icon in the Windows notification area for the life of the
application. The icon reflects the current state: muted grey while stopped,
blue while listening, an accented tone while activated or processing speech,
and amber on an error or degraded state. Hovering shows a short tooltip such
as "Arthur: Listening". Right-clicking opens a context menu with Show Arthur,
Start or Stop listening, Restart (once the runtime is running) and Quit.

Left-clicking the tray icon opens a small popover next to the icon rather than
the full settings panel. The popover shows the current status, a concise
description of the last action and a Listen or Pause control, along with an
Open settings button that brings the main window forward. It never shows
recent transcript text, in keeping with Arthur's local-first privacy stance.
The popover is positioned using the tray icon's bounds and the nearest
display's work area, so it stays clear of the taskbar regardless of which
edge of the screen it sits on, and a second click on the tray icon, a click
outside the popover or the Escape key all close it.

Closing the main panel hides it to the tray instead of quitting Arthur.
Launching Arthur again while it is already running simply brings the existing
window forward. Quitting from the tray menu stops the update timers and the
tray itself, and exits cleanly; it does not stop the Python listener unless it
was already being stopped as part of the same action.

When Arthur enters an activated or dictating state, the tray icon briefly
pulses to the accented tone for well under a second and then returns to its
steady state; it never animates continuously. The Activation glow selector
offers Widget only or Widget + screen. The latter additionally draws a
restrained, click-through outline around the active display for the same brief moment.
Wake events carry a durable activation ID and the desktop watches heartbeat
changes directly, so the cue does not wait for the two-second fallback poll.
The halo is skip-taskbar, never steals focus and is never shown just for
listening.

## Floating indicator

A small floating horizontal mini-panel can stand in for the full
settings panel while Arthur is minimised. It is controlled by the "Show
floating indicator" System preference, which defaults to on, and is kept
entirely separate from the activation halo preference. Closing, minimising or
starting Arthur hidden all hide the settings panel to this background
experience rather than leaving a normal taskbar window; bringing the panel
back up always hides the widget again, so the two surfaces never overlap.

The widget is a small icon-only rectangular control strip matching the main
Electron UI. Its left button starts or stops listening and its right button
opens the full settings panel. A subtle dotted grab handle on the left makes
its draggable behaviour discoverable, with no product logo or transcript text. It runs in a transparent, always-on-top, frameless
window that never appears in the taskbar and cannot be resized. Its state icon
reflects stopped, listening, active or error, and the moment Arthur activates or starts
dictating, a brief radial blue and Copilot-gradient bloom plays for around 800
milliseconds before settling back to its steady presentation. The bloom never
loops, and it is skipped entirely when the operating system requests reduced
motion. Like the popover, the widget never shows recent transcript text or
private command text.

The whole widget is draggable except for its controls button, which stays a
clear no-drag click target and opens the full Arthur settings panel directly.
The compact popover remains exclusive to the Windows notification-area icon.
Its screen position is remembered under LocalAppData and clamped to the
current display's work area on every restore, so a change in monitor layout
can never leave it off-screen. That position is written directly by the main
process as the widget is dragged, on its own debounce, and a renderer
preferences save can never overwrite it.

## Scout boundary

The renderer cannot execute Scout operations. Arthur handles speech and local tools
inside the Python runtime. Requests that need Scout are written to the local handoff
queue for deliberate processing. The desktop app does not enable scheduled
automations or recurring cleanup through Scout. Arthur does not read or write
Scout's private UI settings.

## Security boundaries

- The renderer is sandboxed with Node integration disabled.
- The preload exposes a small typed API only.
- IPC requests, responses and state events are validated with Zod.
- The renderer cannot provide executable paths or arbitrary shell commands.
- Config changes preserve fields outside the desktop settings surface.
- Config writes use atomic temporary-file replacement.
- Voice previews pause Arthur command routing while the preview plays.
- Runtime migration uses fixed local destinations and preserves the source.
- Runtime stop commands are scoped to Arthur's active local directory.
- The tray popover reuses the same sandboxed preload and typed IPC as the main
  window, and denies navigation and new-window requests.
- The tray popover never displays recent transcript text.
- The floating widget reuses the same sandboxed preload, is context isolated
  with Node integration disabled, and denies navigation and new-window
  requests. It never displays recent transcript text or private command text.
- The activation halo window loads no script at all and ignores mouse input.
- Desktop preference changes are persisted with the same atomic write and are
  migrated in place when older preference files are missing newer fields.
- The floating widget's screen position is written only by the main process
  and is not part of the patch schema the renderer sends, so a preferences
  save can never overwrite a position changed by dragging.

## Development

```powershell
npm install
npm run typecheck
npm run lint
npm test
npm run build
npm run test:tray-native
npm start
```

The native tray smoke test requires a completed build. It creates a real
Windows notification-area icon, opens the production popover and floating
widget, exercises their controls, verifies neither surfaces transcript text,
checks that a dragged widget position is persisted through the main process
and verifies the activation halo and widget bloom lifecycles before cleaning
itself up.

Set `ARTHUR_CONFIG` to an existing Arthur config when testing first-run migration
from a custom location.

## Packaging

```powershell
npm run runtime:build
npm run package:nsis
npm run verify:package
```

The package copies the Python source runtime as a sidecar. On first launch,
Arthur downloads a pinned Python distribution, installs pinned speech
dependencies under `%LOCALAPPDATA%\Arthur\python` and verifies the Zipformer
model before using it.

`npm run package:nsis` creates an unsigned local preview. Stable release builds
use `npm run package:release` with the signing credentials supplied by GitHub
Actions.
