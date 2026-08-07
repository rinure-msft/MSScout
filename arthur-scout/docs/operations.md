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

## Install or upgrade

Run the Windows installer from the GitHub Release. It is the supported user
installation and upgrade path.

For development or recovery only:

```powershell
.\install.ps1 -InstallDependencies -InstallSpeechModel
```

To re-verify the default Zipformer model:

```powershell
.\scripts\Install-ArthurZipformerModel.ps1
```

## Update

The Windows installer performs a staged update and rollback automatically.

The installed recovery updater can apply an extracted source package when its
published manifest hash is supplied:

```powershell
& "$env:LOCALAPPDATA\Arthur\runtime\Update-Arthur.ps1" `
  -PackageRoot <extracted-package> `
  -ExpectedManifestSha256 <published-sha256>
```

The update stages the runtime and private Python, installs pinned dependencies,
verifies Zipformer, preserves local state, validates the staged version and
switches directories only after those steps pass.

Use `Start with Windows` in the desktop application. Arthur does not create a scheduled task.

## Cleanup

Arthur cleanup jobs preserve active queue entries and archive completed history. Logs and runtime data stay local unless deliberately exported.

## Scout automations

Scheduled Arthur automations are disabled by default to avoid repeated no-work Scout runs. Email and Scout handoff processors can be run manually when pending work exists.
