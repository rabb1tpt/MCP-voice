#!/usr/bin/env python3
"""
MCP Server for Voice Notes

Records voice notes, transcribes them with Whisper, and saves to a vault inbox.
Configure VAULT_DIR environment variable to set the target vault.
"""

import subprocess
import tempfile
import os
import sys
from datetime import datetime
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Config from environment
VAULT_DIR = Path(os.environ.get("VAULT_DIR", "."))
INBOX_DIR = VAULT_DIR / "inbox"
WHISPER_VENV = Path(os.environ.get("WHISPER_VENV", Path.home() / "code/openai-whisper/.venv"))
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")

server = Server("voice-notes")


def slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    return text.lower().replace(" ", "-").translate(
        str.maketrans("", "", "!@#$%^&*()+=[]{}|;:'\",.<>?/\\`~")
    )


def transcribe_audio(audio_path: str) -> str | None:
    """Transcribe audio using Whisper."""
    try:
        whisper_bin = WHISPER_VENV / "bin" / "whisper"
        temp_dir = os.path.dirname(audio_path)

        subprocess.run(
            [
                str(whisper_bin),
                audio_path,
                "--model", WHISPER_MODEL,
                "--language", "en",
                "--output_dir", temp_dir,
                "--output_format", "txt"
            ],
            check=True,
            capture_output=True,
            timeout=120
        )

        txt_file = audio_path.replace(".wav", ".txt")
        if os.path.exists(txt_file):
            with open(txt_file, "r") as f:
                return f.read().strip()
    except Exception as e:
        print(f"Transcription error: {e}", file=sys.stderr)
        return None
    return None


def cleanup_temp_files(base_path: str):
    """Clean up temporary files created during transcription."""
    for ext in [".wav", ".txt", ".srt", ".vtt", ".json"]:
        temp_file = base_path.replace(".wav", ext)
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="record_voice_note",
            description="Record a voice note, transcribe it with Whisper, and save to the vault inbox. "
                        "This is a blocking call - it starts recording immediately and waits for the user "
                        "to press Enter in the terminal to stop. Use when the user wants to capture thoughts by speaking.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title for the voice note (used in filename). If not provided, uses timestamp."
                    }
                },
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""

    if name == "record_voice_note":
        # Validate VAULT_DIR
        if not INBOX_DIR.exists():
            return [TextContent(
                type="text",
                text=f"Error: Inbox directory not found at {INBOX_DIR}. Check VAULT_DIR environment variable."
            )]

        title = arguments.get("title", "")

        # Generate filename
        if title:
            filename = f"voice-{slugify(title)}.md"
        else:
            filename = f"voice-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.md"

        output_file = INBOX_DIR / filename

        # Check if file exists
        if output_file.exists():
            return [TextContent(
                type="text",
                text=f"Error: File already exists: {filename}. Use a different title."
            )]

        # Create temp file for audio
        fd, temp_audio = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        try:
            # Start recording
            print("\n🎙️  Recording... press Enter to stop\n", file=sys.stderr)

            process = subprocess.Popen(
                ["arecord", "-f", "cd", "-t", "wav", "-q", temp_audio],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Block waiting for Enter
            input()

            # Stop recording
            process.terminate()
            try:
                process.wait(timeout=5)
            except:
                process.kill()

            print("⏳ Transcribing...", file=sys.stderr)

            # Check if audio file exists and has content
            if not os.path.exists(temp_audio) or os.path.getsize(temp_audio) < 1000:
                cleanup_temp_files(temp_audio)
                return [TextContent(type="text", text="Error: No audio captured or recording too short.")]

            # Transcribe
            transcription = transcribe_audio(temp_audio)

            # Cleanup temp files
            cleanup_temp_files(temp_audio)

            if not transcription:
                return [TextContent(type="text", text="Error: Transcription failed or no speech detected.")]

            # Save to inbox
            output_file.write_text(transcription)

            return [TextContent(
                type="text",
                text=f"Voice note saved to inbox/{filename}\n\n--- Transcription ---\n{transcription}"
            )]

        except Exception as e:
            cleanup_temp_files(temp_audio)
            return [TextContent(type="text", text=f"Error: {e}")]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
