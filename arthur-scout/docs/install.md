To install Arthur into another MS Scout instance

Open MS Scout to a new chat prompt.

On your MS Scout prompt, run the following commands:

	git clone https://github.com/rinure-msft/MSScout.git
	%USERPROFILE%\OneDrive - Microsoft\Documents\Microsoft Scout\MSScout\arthur-scout\install.ps1

Then edit the generated local config:

	%USERPROFILE%\OneDrive - Microsoft\Documents\Microsoft Scout\Scratchpad\arthur.config.json

Update placeholders:

	- user name
	- email address
	- microphone index
	- timezone
	- voice
	- Azure DevOps org/project
	- enabled commands

Then start Arthur:

	powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\OneDrive - Microsoft\Documents\Microsoft Scout\Scratchpad\Start-Arthur.ps1"
	
Optional: install Arthur as a Windows sign-in task:

	powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -CreateScheduledTask

After install, validate the package with:

	.\scripts\Test-Arthur.ps1
	
Important: the repo contains only source/templates. Runtime files like queues, logs, heartbeat files, browser profile, audio temp files, and personal history are created locally and are not committed.
