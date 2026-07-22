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

Optionally register Arthur at Windows sign-in:

```powershell
.\install.ps1 -CreateScheduledTask
```

## Cleanup

Arthur cleanup jobs preserve active queue entries and archive completed history. Logs and runtime data stay local unless deliberately exported.
