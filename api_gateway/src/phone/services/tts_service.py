
"""
Text-to-Speech service using Google Cloud Text-to-Speech API
"""

import asyncio
import logging
from typing import Optional, Dict, AsyncGenerator
from google.cloud import texttospeech
import io
import os
from typing import List
from ..config import settings
from ..schema import TTSRequest

logger = logging.getLogger(__name__)


class TTSService:
    """Text-to-Speech service using Google Cloud TTS"""

    def __init__(self):
        """Initialize Google TTS client"""
        # Set up credentials for Google Cloud
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_CREDENTIALS_PATH
        self.client = texttospeech.TextToSpeechClient()

        # Default voice configuration
        self.voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Neural2-F",  # Default to a high-quality neural voice
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
        )

        # Default audio configuration for phone calls
        self.audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MULAW,
            sample_rate_hertz=8000,
            effects_profile_id=["telephony-class-application"],
        )

    async def text_to_speech(self, text: str, voice: str = "en-US-Neural2-F") -> Optional[bytes]:
        """
        Convert text to speech using Google TTS API
        Optimized for low latency
        """
        try:
            # Configure TTS input
            synthesis_input = texttospeech.SynthesisInput(text=text)

            # Update voice if different from default
            voice_params = self.voice
            if voice != "en-US-Neural2-F":
                voice_params = texttospeech.VoiceSelectionParams(
                    language_code="en-US",
                    name=voice,
                    ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
                )

            # Make TTS request in a separate thread to avoid blocking the event loop
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.synthesize_speech(
                    input=synthesis_input,
                    voice=voice_params,
                    audio_config=self.audio_config
                )
            )

            # Return the audio content
            return response.audio_content

        except Exception as e:
            logger.error(f"Error converting text to speech with Google TTS: {str(e)}")
            return None




