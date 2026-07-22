# Arthur Architecture

Arthur is composed of five main runtime layers:

1. Voice bridge: records microphone audio, transcribes speech, matches local voice commands, speaks responses, and queues larger Scout/Copilot tasks.
2. Command registry: maps voice phrases to local handlers or queued prompts.
3. Prompt queue: JSONL queue with pending, claimed, running, completed, failed, and blocked states.
4. Prompt responder automation: Microsoft Scout automation that claims queue entries and executes larger tasks.
5. Supervisor and watchdogs: keep the bridge running, repair stale queue entries, clean local artifacts, and close idle browser sessions.

The default package processes queued tasks serially for safety. Voice capture can continue while the queue responder works in the background.
