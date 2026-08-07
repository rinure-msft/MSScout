# Install Arthur into Microsoft Scout

Download `Arthur-Setup-X.Y.Z-x64.exe` from a tagged GitHub Release and run it.

Arthur installs per user, provisions its private Python runtime and downloads the
verified Zipformer model on first launch.

PowerShell installation remains available for development and recovery:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -InstallDependencies -InstallSpeechModel
```

This installs the same runtime under `%LOCALAPPDATA%\Arthur`.

On a first install, local paths, the Windows timezone and a safe read-only command set are filled automatically. Scout integration remains optional and is never scheduled or synchronized during startup.

Edit:

```text
%LOCALAPPDATA%\Arthur\runtime\arthur.config.json
```

Review the profile and microphone values. Scout and work integrations are
optional and should only be enabled when they are needed.

List current microphone devices when the configured index is stale:

```powershell
python -c "import sounddevice as sd; print(sd.query_devices())"
```

Start Arthur:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\Arthur\runtime\Start-Arthur.ps1"
```

Use `Start with Windows` in the Arthur desktop application when login startup is required. The legacy scheduled task is removed during installation.

Validate the source package:

```powershell
.\scripts\Test-Arthur.ps1
```

The repository contains source and templates only. Model binaries, queues, logs, heartbeat files, browser profiles and personal history remain under LocalAppData. Raw voice-loop audio is not retained.
