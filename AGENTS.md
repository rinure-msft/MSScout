# Working on Arthur with coding agents

This guide applies to GitHub Copilot, Claude and other coding agents working in
this repository. It is deliberately short. Read the code and nearby tests
instead of relying on a maintained file map.

## Start here

1. Read `README.md` and `CONTRIBUTING.md`.
2. Check the current branch and worktree before editing.
3. Read the relevant implementation, tests and documentation together.
4. Make the smallest complete change that solves the problem.
5. Run the narrowest useful validation before broader checks.

## Project boundaries

- `arthur-scout` is the local Python and PowerShell runtime.
- `arthur-desktop` is the Electron application and Windows packaging.
- Runtime data belongs under `%LOCALAPPDATA%\Arthur`, not in the repository.
- Model binaries, audio, logs, queues and personal configuration must not be
  committed.
- Scout, WorkIQ, browser automation and email actions must remain explicit.
- Unknown voice input must never become an unrestricted Scout prompt.

## Development commands

Desktop validation:

```powershell
Set-Location .\arthur-desktop
npm ci
npm run typecheck
npm run lint
npm test
npm run runtime:build
npm run build
npm run verify:package
npm run test:tray-native
```

Runtime validation:

```powershell
.\arthur-scout\scripts\Test-Arthur.ps1
```

Use the existing package managers and scripts. Do not introduce a new build,
test or formatting tool for a small change.

## Safety rules

- Preserve Electron sandboxing, context isolation and blocked navigation.
- Validate IPC input and keep renderer APIs narrow.
- Pass subprocess arguments as arrays. Do not build shell commands from voice
  text or other external input.
- Pin external runtime artifacts and verify their hashes.
- Keep updates staged and reversible.
- Do not weaken command allowlists or confirmation boundaries for convenience.
- Never add secrets, credentials or machine-specific paths.
- Do not execute real Scout, email, approval or browser actions during tests.

## Git and pull requests

- Branch from the latest upstream `main`.
- Keep commits focused and readable.
- Do not mix generated files or unrelated cleanup into a feature change.
- Explain behaviour changes, security impact and test coverage in the pull
  request.
- Treat automatic merges as unreviewed until the combined behaviour is tested.
- Do not commit, tag, push or publish a release unless the task explicitly asks
  for it.

## Documentation

Write for the next contributor, not the current machine. Prefer commands and
behaviour over exact directory listings or screenshots that will quickly age.
Use plain language, short sections and concrete examples. Do not publish local
agent skills, personal paths or details of private development tooling.
