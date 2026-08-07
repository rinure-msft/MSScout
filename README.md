# Arthur

Arthur is a local Windows voice assistant for Microsoft Scout. It listens for a
configured wake name, handles a small set of local commands and hands larger
work to Scout only through explicit, enabled actions.

## Install

Download `Arthur-Setup-0.4.0-x64.exe` from the latest GitHub Release and run it.
Arthur installs for the current user and opens its desktop controls when setup
is complete.

Current releases are unsigned pre-production builds. Windows may show a
SmartScreen warning. Check the published SHA-256 before choosing **Run anyway**.

> [!IMPORTANT]
> Arthur records microphone audio while listening. Normal voice audio is
> processed in memory and is not retained. Runtime state, logs, settings,
> speech models and the private Python environment stay under
> `%LOCALAPPDATA%\Arthur`.
>
> Setup downloads a pinned Python runtime, Python packages and the Zipformer
> speech model. Those downloads are versioned and verified before use. Edge
> neural voices send text to Microsoft's speech service. A Windows voice can
> be selected when fully local speech output is preferred.
>
> Quit Arthur from the notification tray to close the desktop application.
> Uninstall it through Windows Settings. Runtime data is preserved unless the
> user chooses to remove it.

## See it work

1. Open Arthur and select a microphone.
2. Start listening.
3. Minimise the main panel.
4. Say `Arthur`.

The floating widget glows when the wake name is accepted. If screen feedback is
enabled, the active display also shows a short edge glow.

## Getting started

Arthur starts with a small command allowlist. Review the Voice and System pages
before using work integrations. Unknown speech is not forwarded to Scout,
WorkIQ or browser automation.

The Scout bridge is enabled on a fresh install and can be turned off from the
System page. Turning it off blocks new Scout queue entries and stops the local
queue worker. Scheduled Scout automations remain disabled.

The default recogniser is balanced Zipformer INT8. Internal testing measured
8/9 wake recall, 20.6% word error rate and a 0.128 real-time factor on the
project's directional benchmark. The benchmark is useful evidence, not a claim
that the model will perform the same way for every speaker.

## Development

Arthur has two parts:

- `arthur-scout` contains the Python runtime, PowerShell maintenance scripts and
  speech model integration.
- `arthur-desktop` contains the Electron application, tray experience and
  Windows installer.

Contributor setup:

```powershell
git clone https://github.com/rinure-msft/MSScout.git
Set-Location .\MSScout\arthur-desktop
npm ci
npm run typecheck
npm run lint
npm test
npm run runtime:build
npm run build
```

Run the native Windows tray test:

```powershell
npm run test:tray-native
```

Create an unsigned local preview installer:

```powershell
npm run package:nsis
```

Unsigned installers are development artifacts. Stable GitHub releases require
an Authenticode certificate in the release workflow.

<details>
<summary><strong>How the runtime fits together</strong></summary>

The Electron application owns setup, settings, startup behaviour and visible
status. It provisions a private Python runtime and starts Arthur's supervisor.
The supervisor keeps the voice bridge and local workers healthy. The voice
bridge records bounded utterances, transcribes them with Zipformer and routes
only enabled commands.

Large Scout tasks use local queue files. Voice input does not have unrestricted
access to that queue. Model files are downloaded during setup rather than kept
in Git.

</details>

## Privacy and security

Arthur is designed for local operation, but some optional features use network
services:

- Edge neural text-to-speech
- Microsoft Scout and WorkIQ
- GitHub release downloads
- Python and speech model downloads during setup

Do not commit runtime logs, recordings, model binaries, personal configuration
or queue data. See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Coding
agents should also read [AGENTS.md](AGENTS.md).

## Licence

Arthur is available under the [MIT Licence](LICENSE).
