#!/usr/bin/env python3
"""
MCP Server for Voice Notes

Records voice notes, transcribes them with Whisper, and saves to a vault inbox.
Uses webrtcvad for automatic silence detection - no manual stop needed.
Configure VAULT_DIR environment variable to set the target vault.
"""

import subprocess
import tempfile
import os
import sys
import wave
import collections
from datetime import datetime
from pathlib import Path

import pyaudio
import webrtcvad

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Config from environment
VAULT_DIR = Path(os.environ.get("VAULT_DIR", "."))
INBOX_DIR = VAULT_DIR / "inbox"
WHISPER_VENV = Path(os.environ.get("WHISPER_VENV", Path.home() / "code/openai-whisper/.venv"))
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")

# VAD Configuration
SAMPLE_RATE = 16000  # webrtcvad requires 8000, 16000, 32000, or 48000
FRAME_DURATION_MS = 30  # webrtcvad supports 10, 20, or 30 ms
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # samples per frame
VAD_AGGRESSIVENESS = 2  # 0-3, higher = more aggressive filtering
SILENCE_TIMEOUT_SEC = 1.5  # stop after this many seconds of silence
SPEECH_PAD_SEC = 0.3  # padding before/after speech
MAX_RECORDING_SEC = 300  # safety limit: 5 minutes max

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


def notify(title: str, body: str = "", timeout: int = 2000):
    """Send a desktop notification."""
    try:
        cmd = ["notify-send", title, "-t", str(timeout)]
        if body:
            cmd.insert(2, body)
        subprocess.run(cmd, capture_output=True)
    except Exception:
        pass  # Silently fail if notify-send unavailable


def cleanup_temp_files(base_path: str):
    """Clean up temporary files created during transcription."""
    for ext in [".wav", ".txt", ".srt", ".vtt", ".json"]:
        temp_file = base_path.replace(".wav", ext)
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass


def record_with_vad(audio_path: str) -> bool:
    """
    Record audio with voice activity detection.
    Automatically stops after silence is detected.
    Returns True if speech was captured, False otherwise.
    """
    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)

    # Initialize PyAudio
    pa = pyaudio.PyAudio()

    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=FRAME_SIZE
        )
    except Exception as e:
        print(f"Error opening audio stream: {e}", file=sys.stderr)
        pa.terminate()
        return False

    frames = []
    ring_buffer = collections.deque(maxlen=int(SILENCE_TIMEOUT_SEC * 1000 / FRAME_DURATION_MS))
    triggered = False  # Are we currently capturing speech?
    voiced_frames = 0
    total_frames = 0
    max_frames = int(MAX_RECORDING_SEC * 1000 / FRAME_DURATION_MS)

    # Padding buffer for capturing audio just before speech starts
    padding_frames = int(SPEECH_PAD_SEC * 1000 / FRAME_DURATION_MS)
    pre_speech_buffer = collections.deque(maxlen=padding_frames)

    print("🎙️  Listening... (speak now, recording stops after silence)", file=sys.stderr)
    notify("🎙️ Listening...", "Speak now")

    try:
        while total_frames < max_frames:
            try:
                frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
            except Exception as e:
                print(f"Audio read error: {e}", file=sys.stderr)
                break

            total_frames += 1

            # Check if this frame contains speech
            try:
                is_speech = vad.is_speech(frame, SAMPLE_RATE)
            except Exception:
                is_speech = False

            if not triggered:
                # Not yet triggered - looking for speech to start
                pre_speech_buffer.append(frame)

                if is_speech:
                    voiced_frames += 1
                    # Trigger after a few voiced frames to avoid false starts
                    if voiced_frames >= 3:
                        triggered = True
                        print("   Recording...", file=sys.stderr)
                        notify("🔴 Recording...", "Pause to stop")
                        # Add the pre-speech padding
                        frames.extend(pre_speech_buffer)
                        voiced_frames = 0
                else:
                    voiced_frames = 0
            else:
                # Triggered - recording speech, looking for silence to stop
                frames.append(frame)
                ring_buffer.append(is_speech)

                # Check if we have enough silence to stop
                if len(ring_buffer) == ring_buffer.maxlen:
                    num_voiced = sum(ring_buffer)
                    # Stop if less than 10% of recent frames are voiced
                    if num_voiced < len(ring_buffer) * 0.1:
                        print("   Silence detected, stopping.", file=sys.stderr)
                        notify("⏹️ Stopped", "Processing...", timeout=1500)
                        break

        if total_frames >= max_frames:
            print("   Max recording time reached.", file=sys.stderr)

    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

    if not frames:
        print("   No speech detected.", file=sys.stderr)
        return False

    # Write to WAV file
    try:
        with wave.open(audio_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b''.join(frames))
        return True
    except Exception as e:
        print(f"Error writing audio file: {e}", file=sys.stderr)
        return False


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="record_voice_note",
            description="Record a voice note, transcribe it with Whisper, and save to the vault inbox. "
                        "This is a blocking call - it starts recording immediately and automatically stops "
                        "when silence is detected. Use when the user wants to capture thoughts by speaking.",
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
        ),
        Tool(
            name="listen",
            description="Record voice and return the transcription as input for processing. "
                        "Use this when the user wants to speak their request instead of typing. "
                        "Starts recording immediately and stops automatically when silence is detected. "
                        "The transcribed text is returned for Claude to process and respond to.",
            inputSchema={
                "type": "object",
                "properties": {},
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
            # Start recording with VAD
            if not record_with_vad(temp_audio):
                cleanup_temp_files(temp_audio)
                return [TextContent(type="text", text="Error: No speech detected or recording failed.")]

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

    elif name == "listen":
        # Create temp file for audio
        fd, temp_audio = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        try:
            # Start recording with VAD
            if not record_with_vad(temp_audio):
                cleanup_temp_files(temp_audio)
                return [TextContent(type="text", text="Error: No speech detected or recording failed.")]

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

            # Return transcription as user input for Claude to process
            return [TextContent(
                type="text",
                text=f"[Voice input from user]: {transcription}"
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
