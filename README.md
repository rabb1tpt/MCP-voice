# MCP-voice-notes

An MCP server that records voice notes, transcribes them with Whisper, and saves to a vault inbox.

## Setup

### 1. Create virtual environment

```bash
cd ~/Bruno/code/MCP-voice-notes
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure in your project

Add a `.mcp.json` file in your project root:

```json
{
  "mcpServers": {
    "voice-notes": {
      "command": "/home/rabb1tl0ka/Bruno/code/MCP-voice-notes/.venv/bin/python",
      "args": ["/home/rabb1tl0ka/Bruno/code/MCP-voice-notes/server.py"],
      "env": {
        "VAULT_DIR": "/path/to/your/vault"
      }
    }
  }
}
```

### 3. Restart Claude Code

The `record_voice_note` tool will be available.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VAULT_DIR` | Path to the vault (must have an `inbox/` directory) | `.` (current directory) |
| `WHISPER_VENV` | Path to Whisper virtual environment | `~/code/openai-whisper/.venv` |
| `WHISPER_MODEL` | Whisper model to use | `base` |

## Usage

In Claude Code:
- "record Bitcoin thoughts"
- "record meeting notes"

The transcription saves to `{VAULT_DIR}/inbox/voice-{title}.md`.

## Dependencies

- `arecord` (ALSA) for audio recording
- Whisper for transcription (configured via `WHISPER_VENV`)
