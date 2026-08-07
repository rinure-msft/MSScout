# Arthur for Microsoft Scout

Arthur is a local Microsoft Scout voice assistant package with a voice bridge, supervisor, queue watchdog, cleanup jobs and a configurable voice command registry.

Runtime code, configuration templates, maintenance scripts and focused
documentation are kept together in this package. Read the relevant source and
nearby documentation rather than relying on a maintained file tree.

## Package approach

- Source-controlled: scripts, Python modules, templates, docs, command registry.
- Generated on install: `%LOCALAPPDATA%\Arthur\runtime`, private Python, Zipformer model files, queue files, response files, logs, heartbeat and browser profile.
- User-configurable: mic index, threshold, speech model path, timezone, voice, recipient email, ADO project and enabled commands.
- Not committed: model binaries, `*.log`, `*.mp3`, `*.jsonl`, heartbeat files, browser profiles, archives and personal queue history.
- Raw microphone utterances are processed in memory and are not retained by the normal voice loop.

## Speech models

Arthur uses balanced Zipformer INT8 for continuous activation, inline commands and the follow-up utterance after a wake-only activation.

Arthur requires the wake phrase at the start of the utterance, optionally preceded by `hey`, `hay`, `hi`, `ok` or `okay`. It only exposes commands listed in `enabledCommands`. Privileged approval commands are disabled unless deliberately enabled.

Say `Arthur, open dashboard` to open the local status dashboard. The dashboard
is served only on the loopback interface and follows the same visual language
as the desktop tray.

## Recommended install flow

1. Download `Arthur-Setup-X.Y.Z-x64.exe` from a tagged GitHub Release.
2. Run the installer.
3. Open Arthur, select the microphone and review the local settings.
4. Start listening from the application or floating widget.

The installer provisions a verified private Python runtime under `%LOCALAPPDATA%\Arthur\python` and downloads the pinned Zipformer model after verifying its SHA-256 hashes. It does not modify machine-wide Python and it does not register a scheduled task. Use the desktop `Start with Windows` setting when startup is required.

PowerShell installation remains available for development and recovery. It is not the primary user setup experience.

Tagged releases publish both the Windows installer and a source package.

Arthur's Scout automations are installed disabled by default. Run a handoff automation manually only when you intend to spend Scout capacity, until an event-driven processor replaces schedule polling.

The on-demand Scout bridge is enabled on a fresh install and can be turned off
from the desktop System page. This setting is separate from scheduled
automations.

The aggregate model selection results are documented in
`docs\model-selection.md`. Raw benchmark audio is not included.

## Update flow

Run the newer Windows installer to upgrade. Arthur stages the runtime, private Python dependencies and verified speech model before switching versions. The previous runtime is restored if validation or startup fails.

The installed `Update-Arthur.ps1` remains available for recovery and developer packages. Downloaded source updates require the release manifest SHA-256.
