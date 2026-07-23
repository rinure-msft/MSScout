# Arthur Installation Prerequisites

| Requirement | Purpose |
|---|---|
| **Windows 10/11** | Arthur uses PowerShell, Windows audio devices, and optional Scheduled Tasks. |
| **Microsoft Scout installed** | Arthur runs as a local Scout companion and uses Scout automations. |
| **Python 3.12+** | Runs ArthurΓÇÖs voice bridge, supervisor, watchdog, and cleanup scripts. |
| **PowerShell** | Runs `install.ps1`, `Start-Arthur.ps1`, and maintenance scripts. |
| **Git** | Clones the `rinure-msft/MSScout` repository. |
| **GitHub access** | Required to access the private repo. |
| **Microphone access** | Arthur listens through a configured input device index. |
| **Microsoft 365 sign-in in Scout** | Needed for email, calendar, Teams, OneDrive, and WorkIQ-backed commands. |
| **WorkIQ available/authorized** | Used for Microsoft 365 work-context commands. |
| **Playwright/browser access** | Needed for portal automation commands like entitlement approvals. |
| **Network/VPN access to Microsoft internal portals** | Required for CoreIdentity, ADO, ServiceNow, MyAccess, Pulse, WAccess, Personnel, OneVet, etc. |
| **Azure DevOps access** | Required for Arthur Action Tracker commands. |
| **Optional Windows Scheduled Task permission** | Needed if installing Arthur to start at sign-in. |

## Python Modules

Arthur currently imports these Python modules:

```text
edge_tts
numpy
pyttsx3
pygame
sounddevice
faster_whisper
scipy
```
The installer should create local runtime files from templates, but the user must configure 
```arthur.config.json``` with their mic index, email, timezone, ADO project, and enabled command settings.

Required configuration includes:
```text
microphone device index
email address
timezone
Azure DevOps organization/project
enabled command settings
```
