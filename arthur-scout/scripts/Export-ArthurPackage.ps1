param(
    [string] $SourceRoot = 'C:\Users\riur\OneDrive - Microsoft\Documents\Microsoft Scout\Scratchpad',
    [string] $OutputRoot,
    [string] $PrivateRepositoryUrl = 'https://github.com/rinure-msft/MSScout'
)

$ErrorActionPreference = 'Stop'

if (-not $OutputRoot -or $OutputRoot.Trim().Length -eq 0) {
    $OutputRoot = Join-Path (Split-Path -Parent $SourceRoot) 'arthur-scout-package'
}

$PackageRoot = Join-Path $OutputRoot 'arthur-scout'
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path

$RequiredSourceFiles = @(
    'arthur_config.py',
    'arthur_automation_sync.py',
    'arthur_voice_bridge.py',
    'arthur_supervisor.py',
    'arthur_prompt_worker.py',
    'arthur_preflight.py',
    'arthur_email_handoff.py',
    'arthur_scout_handoff.py',
    'arthur_schedule_briefing.py',
    'arthur_status_dashboard.py',
    'arthur_version.py',
    'arthur_queue_watchdog.py',
    'arthur_cleanup_chats.py',
    'arthur_cleanup_recordings.py',
    'arthur_voice_listener_log.py',
    'Start-Arthur.ps1',
    'Update-Arthur.ps1'
)

$RuntimeExcludePatterns = @(
    '*.log',
    '*.wav',
    '*.mp3',
    '*.jsonl',
    '*heartbeat*.json',
    '*state*.json',
    'arthur.version.json',
    'arthur_preflight_status.json',
    'arthur_automation_sync_status.json',
    'arthur_status_dashboard.html',
    'arthur_archive',
    'arthur_edge_profile',
    '__pycache__',
    '*.pyc',
    '*.xlsx',
    '*extracted*.txt',
    'workiq-upload-test.txt'
)

function Write-Status {
    param([string] $Message)
    Write-Host "[Arthur package] $Message"
}

function New-CleanDirectory {
    param([string] $Path)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

function Write-Utf8File {
    param(
        [string] $Path,
        [string] $Content
    )
    $directory = Split-Path -Parent $Path
    if ($directory) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    Set-Content -LiteralPath $Path -Value $Content -Encoding UTF8
}

function Copy-RequiredSource {
    foreach ($fileName in $RequiredSourceFiles) {
        $source = Join-Path $SourceRoot $fileName
        if (-not (Test-Path -LiteralPath $source)) {
            throw "Required Arthur source file not found: $source"
        }

        if ($fileName -like '*.py') {
            $destination = Join-Path $PackageRoot "src\$fileName"
        } else {
            $destination = Join-Path $PackageRoot "scripts\$fileName"
        }

        Copy-Item -LiteralPath $source -Destination $destination -Force
        Write-Status "Copied $fileName"
    }

    $exportScript = $PSCommandPath
    if ($exportScript -and (Test-Path -LiteralPath $exportScript)) {
        Copy-Item -LiteralPath $exportScript -Destination (Join-Path $PackageRoot 'scripts\Export-ArthurPackage.ps1') -Force
    }
}

function Export-VoiceCommands {
    $indexPath = Join-Path $SourceRoot 'arthur_voice_command_index.md'
    $commands = @()

    if (Test-Path -LiteralPath $indexPath) {
        $lines = Get-Content -LiteralPath $indexPath
        foreach ($line in $lines) {
            if ($line -notmatch '^\|\s*\d+\s*\|') {
                continue
            }
            $parts = $line -split '\|'
            if ($parts.Count -lt 6) {
                continue
            }
            $aliases = @()
            foreach ($match in [regex]::Matches($parts[4], '`([^`]+)`')) {
                $aliases += $match.Groups[1].Value
            }
            $commands += [pscustomobject]@{
                name = $parts[2].Trim()
                description = $parts[3].Trim()
                aliases = $aliases
            }
        }
    }

    if ($commands.Count -eq 0) {
        $commands = @(
            [pscustomobject]@{
                name = 'help'
                description = 'List available commands.'
                aliases = @('help', 'what can you do')
            }
        )
    }

    $commands | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $PackageRoot 'config\voice-commands.json') -Encoding UTF8
}

function Write-Templates {
    $configTemplate = @'
{
  "assistantName": "Arthur",
  "userDisplayName": "<YOUR_NAME>",
  "userFirstName": "<YOUR_FIRST_NAME>",
  "timezone": "Mountain Standard Time",
  "voice": {
    "tts": "edge",
    "edgeVoice": "en-US-BrianNeural"
  },
  "greetings": {
    "startup": "good {time_of_day} {name}, I am ready to be of assistance.",
    "updates": "good {time_of_day} {name}, your updates have been applied and I am ready to assist you."
  },
  "microphone": {
    "deviceIndex": 1,
    "threshold": 350,
    "minTranscribeRms": 120,
    "minTranscribePeak": 700
  },
  "notification": {
    "selfEmail": "<YOUR_EMAIL>",
    "teamsSelfMessage": true
  },
  "azureDevOps": {
    "organization": "<ADO_ORGANIZATION>",
    "project": "<ADO_PROJECT>",
    "url": "https://dev.azure.com/<ADO_ORGANIZATION>/<ADO_PROJECT>",
    "tag": "ArthurActionTracker",
    "defaultAssignee": "<YOUR_NAME>",
    "defaultAssigneeEmail": "<YOUR_EMAIL>",
    "defaultWorkItemType": "Task"
  },
  "runtime": {
    "scratchpadPath": "<MS_SCOUT_SCRATCHPAD_PATH>",
    "workiqPath": "<WORKIQ_CMD_PATH>",
    "automationFile": "<SCOUT_AUTOMATIONS_JSON_PATH>",
    "promptResponderAutomationId": "2w51kbs3mqra79xo",
    "cleanupChatArtifactsOlderThanHours": 4,
    "chatCleanupIntervalMinutes": 45,
    "logRetentionDays": 7
  },
  "enabledCommands": [
    "help",
    "voice_command_index",
    "prompt_window",
    "daily_briefing",
    "action_tracker"
  ]
}
'@

    $automationTemplate = @'
[
  {
    "name": "Arthur Copilot prompt responder",
    "description": "Manual fallback for processing Arthur voice prompts in Scout when the local prompt worker blocks or escalates a task.",
    "enabled": false,
    "triggerType": "schedule",
    "schedule": {
      "kind": "interval",
      "naturalLanguage": "every 1 minute",
      "intervalMinutes": 1
    },
    "steps": [
      {
        "id": "1",
        "label": "Main",
        "prompt": "Manual fallback only. Run `python \"<SCRATCHPAD_PATH>\\arthur_queue_watchdog.py\" --claim-next --runner-id \"arthur-scout-fallback-<current timestamp>\"`, then process the claimed prompt using normal Scout safety/privacy rules. Append a response to arthur_prompt_responses.jsonl and mark the queue entry completed, failed, or blocked. Do not leave claimed/running entries stale. Close Playwright after browser automation. Always emit visible status; never stay quiet."
      }
    ]
  },
  {
    "name": "Arthur Email Handoff Sender",
    "description": "Sends self-email handoffs generated by the local Arthur prompt worker and marks handoff entries sent.",
    "enabled": true,
    "triggerType": "schedule",
    "schedule": {
      "kind": "interval",
      "naturalLanguage": "every 5 minutes",
      "intervalMinutes": 5
    },
    "steps": [
      {
        "id": "1",
        "label": "Main",
        "prompt": "Run `python \"<SCRATCHPAD_PATH>\\arthur_email_handoff.py\" --next`. It prints one JSON object. Always produce visible output; never stay quiet. If the helper returns `status` = `no_pending`, respond exactly: `No Arthur email handoff pending.` If the helper returns `status` = `blocked`, respond with the block reason and stop. If `status` = `pending`, inspect `type`. For `self_email`, send using returned `to`, `subject`, `body`, and `is_html`; do not add recipients. For `scout_self_email_prompt`, execute returned `source_prompt` using normal Microsoft 365 tools, generate the requested content, and send only to returned `to`. For Daily Briefing requests, enforce this exact email body structure: start with `Window of time:` and list the window used; then `Sources:` and list Outlook folders and signal types reviewed; then one `Catch Up` section with bold subsection labels `Decisions`, `Actions Needed`, and `FYI Updates`; under each bold subsection, use indented bulleted items. Each indented item must use these labels exactly: `Title`, `What Happened:`, `Why it Matters:`, `Required Action:`, and `Urgency:`. After successful send, run `python \"<SCRATCHPAD_PATH>\\arthur_email_handoff.py\" --mark-sent \"<returned id>\" --response \"<response_after_send or Sent to your inbox.>\"`. Respond exactly with response_after_send, defaulting to `Sent to your inbox.` If sending fails, do not mark sent; report the failure reason."
      }
    ]
  },
  {
    "name": "Arthur Scout Task Handoff Processor",
    "description": "Processes Scout-required Arthur task handoffs such as Action Tracker updates and marks them complete.",
    "enabled": true,
    "triggerType": "schedule",
    "schedule": {
      "kind": "interval",
      "naturalLanguage": "every 2 minutes",
      "intervalMinutes": 2
    },
    "steps": [
      {
        "id": "1",
        "label": "Main",
        "prompt": "Run `python \"<SCRATCHPAD_PATH>\\arthur_scout_handoff.py\" --next`. It prints one JSON object. Always respond visibly; never stay quiet. If status is `no_pending`, respond exactly: `No Arthur Scout handoff pending.` If status is `pending`, inspect `type` and execute the returned `source_prompt` using Scout tools and normal safety/privacy rules. For `type` = `action_tracker`: use the Azure DevOps project named in the returned `source_prompt`, create/update distinct work items tagged `ArthurActionTracker`, assign to the configured assignee unless explicitly different, and send email only to the configured selfEmail recipient specified by the returned `source_prompt`. Do not send Teams messages for Action Tracker handoffs. Close Playwright if used. For `type` = `browser_or_approval`: use Playwright/browser automation if needed, follow the returned `source_prompt`, close Playwright after completion, and send any allowed self-email report only to the configured selfEmail recipient specified by the returned `source_prompt`. Do not send to any other recipient. For `type` = `generic_scout_task`: execute the returned `source_prompt` using available Scout tools. If outbound communication is requested, only proceed when the prompt is explicitly self-addressed to the configured selfEmail recipient; otherwise mark failed with a clear reason. After successful execution, run `python \"<SCRATCHPAD_PATH>\\arthur_scout_handoff.py\" --mark-done \"<returned id>\" --response \"<response_after_completion or Done.>\"` and respond with that response. If execution fails, run `python \"<SCRATCHPAD_PATH>\\arthur_scout_handoff.py\" --mark-failed \"<returned id>\" --reason \"<failure reason>\"` and report the failure."
      }
    ]
  },
  {
    "name": "Arthur Copilot prompt responder Chat Cleanup",
    "description": "Archives Arthur Copilot prompt responder chat/history entries and local chat artifacts older than 4 hours while preserving active queue state.",
    "enabled": true,
    "triggerType": "schedule",
    "schedule": {
      "kind": "interval",
      "naturalLanguage": "every hour",
      "intervalMinutes": 60
    },
    "steps": [
      {
        "id": "1",
        "label": "Delete old responder sessions",
        "prompt": "Search Microsoft Scout sessions for sessions named exactly `Arthur Copilot prompt responder`. Delete sessions older than 4 hours using the Scout session deletion tool. Do not delete the current session, sessions less than 4 hours old, active/open sessions, or sessions with names other than `Arthur Copilot prompt responder`. Always produce a visible count summary; never stay quiet."
      },
      {
        "id": "2",
        "label": "Run local cleanup",
        "prompt": "Run the Arthur chat cleanup script: `python \"<SCRATCHPAD_PATH>\\arthur_cleanup_chats.py\" --max-age-hours 4 --keep-latest-responses 50 --log-retention-days 7`. This archives local Arthur prompt responder history and chat artifacts older than 4 hours. Preserve active pending, claimed, running, blocked, and failed queue entries."
      },
      {
        "id": "3",
        "label": "Report status",
        "prompt": "Report a concise cleanup summary: number of old Scout responder sessions deleted, local artifacts/history archived, active/open sessions skipped, and any errors. If nothing was found, say `Arthur chat cleanup complete. No old responder sessions found.`"
      }
    ]
  }
]
'@

    Write-Utf8File -Path (Join-Path $PackageRoot 'config\arthur.config.template.json') -Content $configTemplate
    $automationTemplatePath = Join-Path $SourceRoot 'automations.template.json'
    if (Test-Path -LiteralPath $automationTemplatePath) {
        Copy-Item -LiteralPath $automationTemplatePath -Destination (Join-Path $PackageRoot 'config\automations.template.json') -Force
    } else {
        Write-Utf8File -Path (Join-Path $PackageRoot 'config\automations.template.json') -Content $automationTemplate
    }
}

function Write-InstallScripts {
    $install = @'
param(
    [string] $InstallRoot = "$env:USERPROFILE\OneDrive - Microsoft\Documents\Microsoft Scout\Scratchpad",
    [switch] $CreateScheduledTask
)

$ErrorActionPreference = 'Stop'

$PackageRoot = Split-Path -Parent $PSCommandPath
$PackageRoot = Split-Path -Parent $PackageRoot

New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null

Copy-Item -LiteralPath (Join-Path $PackageRoot 'src\*.py') -Destination $InstallRoot -Force
Copy-Item -LiteralPath (Join-Path $PackageRoot 'scripts\Start-Arthur.ps1') -Destination $InstallRoot -Force

$configSource = Join-Path $PackageRoot 'config\arthur.config.template.json'
$configTarget = Join-Path $InstallRoot 'arthur.config.json'
if (-not (Test-Path -LiteralPath $configTarget)) {
    Copy-Item -LiteralPath $configSource -Destination $configTarget
    Write-Host "Created config template at $configTarget. Update placeholders before production use."
}

foreach ($file in 'arthur_prompt_queue.jsonl','arthur_prompt_responses.jsonl') {
    $path = Join-Path $InstallRoot $file
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType File -Path $path | Out-Null
    }
}

if ($CreateScheduledTask) {
    $startScript = Join-Path $InstallRoot 'Start-Arthur.ps1'
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    Register-ScheduledTask -TaskName 'Arthur Voice Bridge' -Action $action -Trigger $trigger -Description 'Starts Arthur voice bridge for Microsoft Scout.' -Force | Out-Null
    Write-Host 'Registered scheduled task: Arthur Voice Bridge'
}

Write-Host "Arthur installed to $InstallRoot"
'@

    $uninstall = @'
param(
    [string] $InstallRoot = "$env:USERPROFILE\OneDrive - Microsoft\Documents\Microsoft Scout\Scratchpad",
    [switch] $RemoveRuntimeData
)

$ErrorActionPreference = 'Stop'

Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match 'python' -and ($_.CommandLine -like '*arthur_supervisor.py*' -or $_.CommandLine -like '*arthur_voice_bridge.py*') } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Unregister-ScheduledTask -TaskName 'Arthur Voice Bridge' -Confirm:$false -ErrorAction SilentlyContinue

if ($RemoveRuntimeData -and (Test-Path -LiteralPath $InstallRoot)) {
    Remove-Item -LiteralPath $InstallRoot -Recurse -Force
    Write-Host "Removed Arthur runtime directory: $InstallRoot"
} else {
    Write-Host 'Stopped Arthur and removed scheduled task if present. Runtime files were preserved.'
}
'@

    $test = @'
param(
    [string] $PackageRoot = (Split-Path -Parent (Split-Path -Parent $PSCommandPath))
)

$ErrorActionPreference = 'Stop'

$required = @(
    'src\arthur_config.py',
    'src\arthur_voice_bridge.py',
    'src\arthur_supervisor.py',
    'src\arthur_prompt_worker.py',
    'src\arthur_email_handoff.py',
    'src\arthur_scout_handoff.py',
    'src\arthur_queue_watchdog.py',
    'src\arthur_cleanup_chats.py',
    'src\arthur_cleanup_recordings.py',
    'src\arthur_voice_listener_log.py',
    'scripts\Start-Arthur.ps1',
    'config\arthur.config.template.json',
    'config\voice-commands.json',
    'config\automations.template.json'
)

foreach ($relative in $required) {
    $path = Join-Path $PackageRoot $relative
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing required package file: $relative"
    }
}

python -m py_compile (Join-Path $PackageRoot 'src\arthur_config.py') (Join-Path $PackageRoot 'src\arthur_voice_bridge.py') (Join-Path $PackageRoot 'src\arthur_supervisor.py') (Join-Path $PackageRoot 'src\arthur_prompt_worker.py') (Join-Path $PackageRoot 'src\arthur_email_handoff.py') (Join-Path $PackageRoot 'src\arthur_scout_handoff.py') (Join-Path $PackageRoot 'src\arthur_queue_watchdog.py') (Join-Path $PackageRoot 'src\arthur_cleanup_chats.py') (Join-Path $PackageRoot 'src\arthur_cleanup_recordings.py') (Join-Path $PackageRoot 'src\arthur_voice_listener_log.py')
Get-ChildItem -LiteralPath (Join-Path $PackageRoot 'src') -Directory -Filter '__pycache__' -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Get-Content -LiteralPath (Join-Path $PackageRoot 'config\arthur.config.template.json') -Raw | ConvertFrom-Json | Out-Null
Get-Content -LiteralPath (Join-Path $PackageRoot 'config\voice-commands.json') -Raw | ConvertFrom-Json | Out-Null
Get-Content -LiteralPath (Join-Path $PackageRoot 'config\automations.template.json') -Raw | ConvertFrom-Json | Out-Null

Write-Host 'Arthur package validation passed.'
'@

    Write-Utf8File -Path (Join-Path $PackageRoot 'install.ps1') -Content $install
    Write-Utf8File -Path (Join-Path $PackageRoot 'uninstall.ps1') -Content $uninstall
    Write-Utf8File -Path (Join-Path $PackageRoot 'scripts\Test-Arthur.ps1') -Content $test
}

function Write-Docs {
    $readme = @"
# Arthur for Microsoft Scout

Arthur is a local Microsoft Scout voice assistant package with a voice bridge, supervisor, queue watchdog, cleanup jobs, and a configurable voice command registry.

Private repository target: $PrivateRepositoryUrl

## Package layout

````text
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
````

## Package approach

- Source-controlled: scripts, Python modules, templates, docs, command registry.
- Generated on install: local Scratchpad runtime folder, queue files, response files, logs, heartbeat, browser profile, audio temp files.
- User-configurable: mic index, threshold, timezone, voice, recipient email, ADO project, enabled commands.
- Not committed: `*.log`, `*.wav`, `*.mp3`, `*.jsonl`, heartbeat files, browser profiles, archives, personal queue history.

## Recommended install flow

1. Clone repo.
2. Run `install.ps1`.
3. Installer copies Arthur files into Scout Scratchpad or a chosen install directory.
4. Installer creates local config from template.
5. Installer registers/updates Scout automation prompt.
6. Installer optionally creates Windows scheduled task: Arthur Voice Bridge.
7. Run `Start-Arthur.ps1`.
"@

    $architecture = @'
# Arthur Architecture

Arthur is composed of five main runtime layers:

1. Voice bridge: records microphone audio, transcribes speech, matches local voice commands, speaks responses, and queues larger Scout/Copilot tasks.
2. Command registry: maps voice phrases to local handlers or queued prompts.
3. Prompt queue: JSONL queue with pending, claimed, running, completed, failed, and blocked states.
4. Prompt responder automation: Microsoft Scout automation that claims queue entries and executes larger tasks.
5. Supervisor and watchdogs: keep the bridge running, repair stale queue entries, clean local artifacts, and close idle browser sessions.

The default package processes queued tasks serially for safety. Voice capture can continue while the queue responder works in the background.
'@

    $fileStructure = @'
# Arthur File Structure

Source-controlled files are packaged under:

```text
arthur-scout/
  config/
  docs/
  scripts/
  src/
```

Runtime files are generated locally during install and operation:

- `arthur_prompt_queue.jsonl`
- `arthur_prompt_responses.jsonl`
- `arthur_voice_bridge_heartbeat.json`
- `arthur_*.log`
- `arthur_bridge_utterance_*.wav`
- `arthur_edge_tts_*.mp3`
- `arthur_edge_profile/`
- `arthur_archive/`

Runtime files should not be committed.
'@

    $operations = @'
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
'@

    $voiceCommandDoc = "# Arthur Voice Command Registry`r`n`r`nThe exported command registry is stored in ``config\voice-commands.json``. The source runtime index is generated by Arthur as ``arthur_voice_command_index.md``.`r`n"
    $sourceIndex = Join-Path $SourceRoot 'arthur_voice_command_index.md'
    if (Test-Path -LiteralPath $sourceIndex) {
        $voiceCommandDoc += "`r`n## Current exported index`r`n`r`n"
        $voiceCommandDoc += (Get-Content -LiteralPath $sourceIndex -Raw)
    }

    Write-Utf8File -Path (Join-Path $PackageRoot 'README.md') -Content $readme
    Write-Utf8File -Path (Join-Path $PackageRoot 'docs\architecture.md') -Content $architecture
    Write-Utf8File -Path (Join-Path $PackageRoot 'docs\file-structure.md') -Content $fileStructure
    Write-Utf8File -Path (Join-Path $PackageRoot 'docs\operations.md') -Content $operations
    Write-Utf8File -Path (Join-Path $PackageRoot 'docs\voice-command-registry.md') -Content $voiceCommandDoc
}

function Write-GitIgnore {
    $gitignore = @'
# Arthur runtime and private artifacts
*.log
*.wav
*.mp3
*.jsonl
*heartbeat*.json
*state*.json
arthur_archive/
arthur_edge_profile/
__pycache__/
*.pyc

# Local config generated from template
arthur.config.json

# Office/export artifacts and scratch data
*.xlsx
*extracted*.txt
workiq-upload-test.txt
'@
    Write-Utf8File -Path (Join-Path $PackageRoot '.gitignore') -Content $gitignore
}

Write-Status "Building clean Arthur package at $PackageRoot"
New-CleanDirectory -Path $PackageRoot
foreach ($directory in 'config','src','scripts','docs') {
    New-Item -ItemType Directory -Path (Join-Path $PackageRoot $directory) -Force | Out-Null
}

Copy-RequiredSource
Export-VoiceCommands
Write-Templates
Write-InstallScripts
Write-Docs
Write-GitIgnore

Write-Status 'Validating package manifest.'
$expected = @(
    'README.md',
    'install.ps1',
    'uninstall.ps1',
    'config\arthur.config.template.json',
    'config\voice-commands.json',
    'config\automations.template.json',
    'src\arthur_config.py',
    'src\arthur_voice_bridge.py',
    'src\arthur_supervisor.py',
    'src\arthur_prompt_worker.py',
    'src\arthur_email_handoff.py',
    'src\arthur_scout_handoff.py',
    'src\arthur_queue_watchdog.py',
    'src\arthur_cleanup_chats.py',
    'src\arthur_cleanup_recordings.py',
    'src\arthur_voice_listener_log.py',
    'scripts\Start-Arthur.ps1',
    'scripts\Test-Arthur.ps1',
    'scripts\Export-ArthurPackage.ps1',
    'docs\architecture.md',
    'docs\file-structure.md',
    'docs\voice-command-registry.md',
    'docs\operations.md',
    '.gitignore'
)

foreach ($relative in $expected) {
    $path = Join-Path $PackageRoot $relative
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Package file missing: $relative"
    }
}

Write-Status "Package complete: $PackageRoot"
