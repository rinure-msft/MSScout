# Arthur Operations

## Start

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Arthur.ps1
```

## Validate package

Run:

```powershell
.\scripts\Test-Arthur.ps1
```

## Install

Run:

```powershell
.\install.ps1
```

## Update

Run from a downloaded or cloned package:

```powershell
.\scripts\Update-Arthur.ps1
```

The update copies package files into the live Scratchpad, preserves `arthur.config.json`, runs config validation, preflight checks, no-side-effect voice command smoke tests, syncs automations, regenerates the dashboard, restarts Arthur, and writes `arthur_update_report.json`.

Optionally register Arthur at Windows sign-in:

```powershell
.\install.ps1 -CreateScheduledTask
```

## Cleanup

Arthur cleanup jobs preserve active queue entries and archive completed history. Logs and runtime data stay local unless deliberately exported.
