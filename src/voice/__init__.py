"""
Voice interface for Odoo ERP Interview Agent.

Provides speech-to-text and text-to-speech capabilities for
conducting interviews via voice instead of text.

Components:
- SpeechToText: Uses faster-whisper for local transcription
- TextToSpeech: ElevenLabs (natural voices) with pyttsx3 fallback
- VoiceInterviewAgent: Combines both for voice-based interviews
"""

from .speech_to_text import SpeechToText, transcribe_audio_file
from .text_to_speech import TextToSpeech, ELEVENLABS_VOICES
from .voice_agent import VoiceInterviewAgent

__all__ = [
    "SpeechToText",
    "TextToSpeech",
    "ELEVENLABS_VOICES",
    "VoiceInterviewAgent",
    "transcribe_audio_file"
]
