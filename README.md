# MCP-voice

An MCP server for voice input - record voice notes or speak commands for Claude to process.

## Setup

### 1. Create virtual environment

```bash
cd ~/Bruno/code/MCP-voice
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure in your project

Add a `.mcp.json` file in your project root:

```json
{
  "mcpServers": {
    "voice": {
      "command": "/path/to/MCP-voice/.venv/bin/python",
      "args": ["/path/to/MCP-voice/server.py"],
      "env": {
        "VAULT_DIR": "/path/to/your/vault"
      }
    }
  }
}
```

### 3. Restart Claude Code

The voice tools will be available.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VAULT_DIR` | Path to the vault (must have an `inbox/` directory) | `.` (current directory) |
| `WHISPER_VENV` | Path to Whisper virtual environment | `~/code/openai-whisper/.venv` |
| `WHISPER_MODEL` | Whisper model to use | `base` |

## Tools

| Tool | Description |
|------|-------------|
| `record_voice_note` | Record, transcribe, and save to vault inbox |
| `listen` | Record, transcribe, and return as input for Claude to process |

## Usage

In Claude Code:
- "record Bitcoin thoughts" - saves transcription to inbox
- "listen" - speak your request, Claude processes it

## Dependencies

- `arecord` (ALSA) for audio recording
- Whisper for transcription (configured via `WHISPER_VENV`)
