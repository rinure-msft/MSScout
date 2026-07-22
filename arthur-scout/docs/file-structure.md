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
