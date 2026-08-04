# Arthur for Microsoft Scout

Arthur is a local Microsoft Scout voice assistant package with a voice bridge, supervisor, queue watchdog, cleanup jobs, and a configurable voice command registry.

Private repository target: https://github.com/rinure-msft/MSScout

## Package layout

``text
arthur-scout/
  README.md
  install.ps1
  uninstall.ps1
  config/
    arthur.config.template.json
    voice-commands.json
    automations.template.json
  src/
    arthur_config.py
    arthur_voice_bridge.py
    arthur_supervisor.py
    arthur_prompt_worker.py
    arthur_email_handoff.py
    arthur_scout_handoff.py
    arthur_queue_watchdog.py
    arthur_cleanup_chats.py
    arthur_cleanup_recordings.py
    arthur_voice_listener_log.py
  scripts/
    Start-Arthur.ps1
    Test-Arthur.ps1
    Export-ArthurPackage.ps1
  docs/
    architecture.md
    file-structure.md
    voice-command-registry.md
    operations.md
  .gitignore
``

## Package approach

- Source-controlled: scripts, Python modules, templates, docs, command registry.
- Generated on install: local Scratchpad runtime folder, queue files, response files, logs, heartbeat, browser profile, audio temp files.
- User-configurable: mic index, threshold, timezone, voice, recipient email, ADO project, enabled commands.
- Not committed: *.log, *.wav, *.mp3, *.jsonl, heartbeat files, browser profiles, archives, personal queue history.

## Recommended install flow

1. Download the `arthur-scout-vX.Y.Z.zip` asset from a tagged GitHub Release, or clone the repo for development.
2. Extract the zip.
3. Run `install.ps1`.
4. Installer copies Arthur files into Scout Scratchpad or a chosen install directory.
5. Installer creates local config from template.
6. Fill `arthur.config.json` placeholders.
7. Run `Start-Arthur.ps1`.

Tagged releases are published from tags like `v0.2.0`. Each release asset is a clean zipped `arthur-scout` package built by GitHub Actions.

## Update flow

Run `scripts\Update-Arthur.ps1` from a downloaded or cloned package to copy package files into the live Scratchpad, preserve `arthur.config.json`, run config/preflight/smoke checks, sync automations, regenerate the dashboard, restart Arthur, and write `arthur_update_report.json`.
