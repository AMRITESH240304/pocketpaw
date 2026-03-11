# Text-to-Speech tool — synthesize audio via ElevenLabs, OpenAI, or Sarvam.
# Created: 2026-03-11
# Part of Phase 4 Media Integrations

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import httpx

from pocketpaw.config import get_config_dir, get_settings
from pocketpaw.tools.protocol import BaseTool

logger = logging.getLogger(__name__)


def _get_audio_dir() -> Path:
    """Get/create the audio output directory."""
    d = get_config_dir() / "generated" / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def synthesize_speech(text: str) -> str | None:
    """Standalone helper: synthesize text to an MP3 file using configured TTS provider.

    Returns the output file path on success, or None on failure.
    Designed for use by the agent loop (auto-TTS for voice replies).
    """
    tool = TextToSpeechTool()
    await tool.execute(text=text)
    return tool._last_generated_path


class TextToSpeechTool(BaseTool):
    """Convert text to speech audio using ElevenLabs, OpenAI TTS, or Sarvam AI."""

    def __init__(self) -> None:
        # Populated after a successful synthesis; read by synthesize_speech()
        self._last_generated_path: str | None = None

    @property
    def name(self) -> str:
        return "text_to_speech"

    @property
    def description(self) -> str:
        return (
            "Convert text to a speech audio file. "
            "Supports ElevenLabs (eleven_multilingual_v2, streaming), "
            "OpenAI TTS (tts-1), and Sarvam AI Bulbul (Indian languages). "
            "Output saved to ~/.pocketpaw/generated/audio/ as MP3 or WAV. "
            "Use this when the user sent a voice message and expects a voice reply."
            "Do not describe or link the output file."
        )

    @property
    def trust_level(self) -> str:
        return "standard"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to convert to speech",
                },
                "voice": {
                    "type": "string",
                    "description": (
                        "Voice ID or name. "
                        "ElevenLabs: voice ID (e.g. 'JBFqnCBsd6RMkjVDRZzb'); "
                        "OpenAI: alloy/echo/fable/onyx/nova/shimmer; "
                        "Sarvam: Shubh/Kriti/Amol/Amartya/Diya/Neel/Maitreyi/Vian."
                    ),
                },
            },
            "required": ["text"],
        }

    async def execute(self, text: str, voice: str | None = None) -> str:
        if not text or not text.strip():
            return self._error("No text provided for speech synthesis.")

        settings = get_settings()
        provider = settings.tts_provider
        voice = voice or settings.tts_voice

        if provider == "elevenlabs":
            return await self._tts_elevenlabs(text, voice)
        else:
            return self._error(
                f"Unknown TTS provider: {provider!r}. Choose 'elevenlabs'"
            )

    async def _tts_elevenlabs(self, text: str, voice: str) -> str:
        """Synthesize speech via ElevenLabs streaming API."""
        settings = get_settings()
        api_key = settings.elevenlabs_api_key
        if not api_key:
            return self._error(
                "ElevenLabs API key not configured. Set POCKETPAW_ELEVENLABS_API_KEY."
            )

        # Default to a good multilingual voice if the OpenAI default "alloy" slipped through
        if not voice or voice in ("alloy", "echo", "fable", "onyx", "nova", "shimmer"):
            voice = "JBFqnCBsd6RMkjVDRZzb"

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream",
                    headers={
                        "xi-api-key": api_key,
                        "Content-Type": "application/json",
                    },
                    params={"output_format": "mp3_44100_128"},
                    json={
                        "text": text[:5000],
                        "model_id": "eleven_multilingual_v2",
                    },
                )
                resp.raise_for_status()
                audio_bytes = resp.content

            filename = f"tts_{uuid.uuid4().hex[:8]}.mp3"
            output_path = _get_audio_dir() / filename
            output_path.write_bytes(audio_bytes)

            logger.info("ElevenLabs TTS: generated %s (%d bytes)", filename, len(audio_bytes))
            self._last_generated_path = str(output_path)
            return self._media_result(str(output_path))
            # return self._error(f"ElevenLabs TTS error: {e.response.status_code}")
        except Exception as e:
            return self._error(f"ElevenLabs TTS failed: {e}")
        