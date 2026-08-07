# Contributing to Arthur

Arthur is a small project moving quickly. Contributions should be easy to
review, easy to test and narrow enough to change again later.

## Set up locally

Arthur development currently targets Windows 10 or 11.

```powershell
git clone https://github.com/rinure-msft/MSScout.git
Set-Location .\MSScout\arthur-desktop
npm ci
```

The desktop build packages the Python runtime from `arthur-scout`. A separate
machine-wide Python installation is not required for normal application use.
Runtime contributors may use Python directly for focused checks.

## Make a change

1. Fetch the latest upstream `main`.
2. Create a short-lived branch for one change.
3. Read the implementation and its tests before editing.
4. Add or update tests when behaviour changes.
5. Update documentation only where the change affects users or contributors.

Do not commit models, audio, logs, generated installers, personal settings or
LocalAppData runtime state.

## Validate

For desktop changes:

```powershell
Set-Location .\arthur-desktop
npm run typecheck
npm run lint
npm test
npm run runtime:build
npm run build
npm run verify:package
```

Run `npm run test:tray-native` for tray, widget, activation or window lifecycle
changes.

For runtime changes:

```powershell
.\arthur-scout\scripts\Test-Arthur.ps1
```

Tests must not send email, invoke real Scout work, approve requests or retain
microphone recordings.

## Open a pull request

Use a clear title and explain:

- what changed
- why the change is needed
- any user-visible or security impact
- how it was tested
- any known limitation or follow-up

Keep the pull request focused. Large features can use several logical commits
without being split into unnecessary administrative pull requests.

## Review pull requests

Review behaviour before style. Check the security boundary, failure handling,
upgrade compatibility and tests. For speech changes, include measured results
and the limits of the benchmark. For packaging changes, check fresh install,
upgrade and rollback paths.

Use specific comments tied to code or observable behaviour. Avoid blocking a
change over personal formatting preferences when the repository already has a
consistent pattern.

## Pre-release installers

Current GitHub releases are unsigned pre-production builds. Windows may show a
SmartScreen warning. Verify the SHA-256 published with the installer before
running it. Authenticode signing will be added before a production release.
