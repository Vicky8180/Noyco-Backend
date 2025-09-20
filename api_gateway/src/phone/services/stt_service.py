

# """
# Speech-to-Text service using Google Cloud Speech-to-Text API with Streaming Support
# """

# import asyncio
# import logging
# import io
# from typing import Optional, AsyncGenerator
# from google.cloud import speech
# import os
# import threading
# from concurrent.futures import ThreadPoolExecutor

# from ..config import settings
# from ..schema import TranscriptionResult

# logger = logging.getLogger(__name__)


# class STTService:
#     """Speech-to-Text service with real-time streaming capabilities"""

#     def __init__(self):
#         # Set up credentials for Google Cloud
#         os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_CREDENTIALS_PATH
#         self.client = speech.SpeechClient()

#         # Thread pool for parallel processing
#         self.thread_pool = ThreadPoolExecutor(max_workers=3)

#         # Base configuration for phone calls
#         self.base_config = speech.RecognitionConfig(
#             encoding=speech.RecognitionConfig.AudioEncoding.MULAW,
#             sample_rate_hertz=8000,
#             language_code="en-US",
#             model="phone_call",
#             use_enhanced=True,
#             enable_automatic_punctuation=True,
#             audio_channel_count=1,
#             profanity_filter=False,
#             speech_contexts=[speech.SpeechContext(
#                 phrases=["paracetamol", "medication", "prescription", "doctor", "treatment", "symptoms"],
#                 boost=15.0
#             )]
#         )

#         # Optimized config for partial results (faster, less accurate)
#         self.partial_config = speech.RecognitionConfig(
#             encoding=speech.RecognitionConfig.AudioEncoding.MULAW,
#             sample_rate_hertz=8000,
#             language_code="en-US",
#             model="phone_call",
#             use_enhanced=False,  # Faster processing
#             enable_automatic_punctuation=False,  # Faster processing
#             max_alternatives=1,
#             audio_channel_count=1,
#             profanity_filter=False
#         )

#         # Optimized config for final results (slower, more accurate)
#         self.final_config = speech.RecognitionConfig(
#             encoding=speech.RecognitionConfig.AudioEncoding.MULAW,
#             sample_rate_hertz=8000,
#             language_code="en-US",
#             model="phone_call",
#             use_enhanced=True,
#             enable_automatic_punctuation=True,
#             enable_word_time_offsets=True,
#             max_alternatives=3,
#             audio_channel_count=1,
#             profanity_filter=False,
#             speech_contexts=self.base_config.speech_contexts
#         )

#     async def transcribe_audio(self, audio_data: bytes, is_final: bool = False) -> Optional[TranscriptionResult]:
#         """
#         Transcribe audio with optimized configuration based on finality requirement
#         """
#         if len(audio_data) < 160:  # Less than 20ms of audio
#             return None

#         try:
#             # Create recognition audio
#             audio = speech.RecognitionAudio(content=audio_data)

#             # Choose config based on finality requirement
#             config = self.final_config if is_final else self.partial_config

#             # Run transcription in thread pool to avoid blocking
#             response = await asyncio.get_event_loop().run_in_executor(
#                 self.thread_pool,
#                 lambda: self.client.recognize(config=config, audio=audio)
#             )

#             # Process results
#             if response.results and len(response.results) > 0:
#                 result = response.results[0]

#                 if result.alternatives and len(result.alternatives) > 0:
#                     # For final results, choose best alternative
#                     if is_final and len(result.alternatives) > 1:
#                         alternatives = sorted(
#                             result.alternatives,
#                             key=lambda alt: getattr(alt, 'confidence', 0),
#                             reverse=True
#                         )
#                         best_alt = alternatives[0]
#                     else:
#                         best_alt = result.alternatives[0]

#                     # Filter out very short or nonsensical results
#                     text = best_alt.transcript.strip()
#                     if len(text) < 2:
#                         return None

#                     confidence = getattr(best_alt, 'confidence', 0.0)

#                     # For partial results, accept lower confidence
#                     # For final results, require higher confidence
#                     min_confidence = 0.3 if not is_final else 0.5

#                     if confidence < min_confidence and is_final:
#                         logger.debug(f"Low confidence transcription rejected: {text} ({confidence})")
#                         return None

#                     return TranscriptionResult(
#                         text=text,
#                         confidence=confidence,
#                         is_final=is_final
#                     )

#             return None

#         except Exception as e:
#             logger.error(f"Error transcribing audio: {str(e)}")
#             return None

#     async def stream_transcribe_audio(self, audio_stream: AsyncGenerator[bytes, None]) -> AsyncGenerator[TranscriptionResult, None]:
#         """
#         Stream transcription for continuous audio input
#         """
#         try:
#             # Configure streaming recognition
#             streaming_config = speech.StreamingRecognitionConfig(
#                 config=self.base_config,
#                 interim_results=True,
#                 single_utterance=False
#             )

#             # Create streaming request generator
#             async def request_generator():
#                 yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)

#                 async for audio_chunk in audio_stream:
#                     if audio_chunk:
#                         yield speech.StreamingRecognizeRequest(audio_content=audio_chunk)

#             # Process streaming responses
#             responses = await asyncio.get_event_loop().run_in_executor(
#                 self.thread_pool,
#                 lambda: self.client.streaming_recognize(request_generator())
#             )

#             for response in responses:
#                 for result in response.results:
#                     if result.alternatives:
#                         text = result.alternatives[0].transcript
#                         confidence = getattr(result.alternatives[0], 'confidence', 0.0)

#                         yield TranscriptionResult(
#                             text=text,
#                             confidence=confidence,
#                             is_final=result.is_final
#                         )

#         except Exception as e:
#             logger.error(f"Error in streaming transcription: {str(e)}")
#             return

