"""
Gemini Live relay — pipes browser audio to a Gemini Live session and streams
transcriptions (STT) + synthesized audio (TTS) back to the browser.

The Gemini API key stays server-side; the browser only talks to this FastAPI
WebSocket endpoint.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from google import genai
from google.genai import types

from backend.config import load_env

INPUT_SAMPLE_RATE = 16000


class GeminiLiveRelay:
    """Wraps a Gemini Live session with server-side key handling."""

    def __init__(
        self,
        system_prompt: str,
        model: str | None = None,
        voice: str | None = None,
        api_key: str | None = None,
    ) -> None:
        load_env()
        self.system_prompt = system_prompt
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = model or os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
        self.voice = voice or os.getenv("GEMINI_LIVE_VOICE", "Puck")
        self._client = genai.Client(api_key=self.api_key) if self.api_key else None
        self._session: Any = None

    @property
    def available(self) -> bool:
        return bool(self.api_key and self._client)

    def _config(self) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            system_instruction=types.Content(
                parts=[types.Part(text=self.system_prompt)]
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice
                    )
                )
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            # Automatic VAD stays enabled (Gemini's default): we stream mic audio
            # continuously and Gemini's built-in voice detection controls turn
            # boundaries. Manual activity_start/activity_end windowing was fragile
            # and crashed with "1007 Precondition check failed".
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(target_tokens=20000)
            ),
        )

    @asynccontextmanager
    async def connect(self) -> AsyncIterator["AsyncSession"]:
        """Open a Gemini Live session and yield it as an async context manager."""
        if not self._client:
            raise RuntimeError("Gemini Live is not configured (missing API key).")
        async with self._client.aio.live.connect(
            model=self.model, config=self._config()
        ) as session:
            self._session = session
            try:
                yield session
            finally:
                self._session = None

    @staticmethod
    async def send_audio(session, data: bytes) -> None:
        await session.send_realtime_input(
            audio=types.Blob(
                data=data, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}"
            )
        )

    @staticmethod
    async def audio_stream_end(session) -> None:
        """Flush buffered audio so Gemini finalizes the current user turn (hybrid VAD)."""
        await session.send_realtime_input(audio_stream_end=True)

    @staticmethod
    async def begin_interview(session) -> None:
        """Seed the first turn so the interviewer delivers its opening greeting."""
        await session.send_client_content(
            turns={
                "role": "user",
                "parts": [
                    {"text": "Please begin the interview with your opening greeting."}
                ],
            },
            turn_complete=True,
        )
