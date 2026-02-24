"""
Voice CLI for Odoo ERP Interview Agent.

Run voice-based interviews from the command line.
"""

import argparse
import sys


def print_header():
    """Print CLI header."""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║     ODOO ERP IMPLEMENTATION AGENT - Voice Interview           ║
║                                                               ║
║     Speak your answers - AI transcribes and processes         ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """)


def check_dependencies():
    """Check if voice dependencies are installed."""
    missing = []

    try:
        import faster_whisper
    except ImportError:
        missing.append("faster-whisper")

    try:
        import pyttsx3
    except ImportError:
        missing.append("pyttsx3")

    try:
        import sounddevice
    except ImportError:
        missing.append("sounddevice")

    try:
        import numpy
    except ImportError:
        missing.append("numpy")

    if missing:
        print("Missing voice dependencies:")
        for dep in missing:
            print(f"   - {dep}")
        print("\nInstall with:")
        print("   pip install odoo-erp-agent[voice]")
        print("   # or")
        print("   pip install faster-whisper pyttsx3 sounddevice numpy")
        return False

    # Check ElevenLabs setup (optional)
    import os
    if os.environ.get("ELEVENLABS_API_KEY"):
        print("   ElevenLabs API key detected - natural voices enabled")
    else:
        print("   Tip: Set ELEVENLABS_API_KEY for natural-sounding voices")

    return True


def test_audio():
    """Test audio input/output."""
    print("\nTesting text-to-speech...")
    try:
        from src.voice.text_to_speech import TextToSpeech
        tts = TextToSpeech(rate=160)
        print(f"   Provider: {tts.provider}")
        tts.speak("Audio test successful. Text to speech is working.")
        print("   Text-to-speech working")
    except Exception as e:
        print(f"   Text-to-speech failed: {e}")
        return False

    print("\n🎤 Testing microphone (speak something)...")
    try:
        from src.voice.speech_to_text import MicrophoneRecorder, SpeechToText

        recorder = MicrophoneRecorder()
        print("   Recording for 3 seconds...")

        audio = recorder.record_fixed_duration(3.0)

        if len(audio) > 0:
            print(f"   ✓ Recorded {len(audio)} samples")

            print("   Transcribing...")
            stt = SpeechToText(model_size="tiny")  # Use tiny for quick test
            result = stt.transcribe(audio)
            print(f"   ✓ Transcribed: \"{result.text}\"")
        else:
            print("   ✗ No audio recorded")
            return False

    except Exception as e:
        print(f"   ✗ Microphone test failed: {e}")
        return False

    print("\n✅ All audio tests passed!")
    return True


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Odoo ERP Voice Interview Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start a voice interview
  python -m src.voice_cli --client "ACME Corp" --industry "Manufacturing"

  # Use a larger Whisper model for better accuracy
  python -m src.voice_cli --client "ACME Corp" --industry "Retail" --model small

  # Test audio setup
  python -m src.voice_cli --test-audio

  # Ask for client & industry via voice
  python -m src.voice_cli

  # Disable LLM (rule-based only)
  python -m src.voice_cli --client "ACME Corp" --industry "Services" --no-llm
        """
    )

    parser.add_argument(
        "--client", "-c",
        help="Client/company name"
    )

    parser.add_argument(
        "--industry", "-i",
        help="Client industry (e.g., Manufacturing, Retail, Services)"
    )

    parser.add_argument(
        "--model", "-m",
        default="base",
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Whisper model size (default: base)"
    )

    parser.add_argument(
        "--language", "-l",
        default="en",
        help="Language code (default: en)"
    )

    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM enhancement (faster, rule-based only)"
    )

    parser.add_argument(
        "--test-audio",
        action="store_true",
        help="Test audio input/output and exit"
    )

    parser.add_argument(
        "--voice", "-v",
        default=None,
        help="ElevenLabs voice name (e.g., rachel, adam, sarah, jessica, chris)"
    )

    parser.add_argument(
        "--output", "-o",
        default="./outputs",
        help="Output directory for generated files"
    )

    args = parser.parse_args()

    print_header()

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Test audio mode
    if args.test_audio:
        success = test_audio()
        sys.exit(0 if success else 1)

    # Run voice interview
    from src.voice.voice_agent import VoiceInterviewAgent, VoiceConfig

    config = VoiceConfig(
        whisper_model=args.model,
        language=args.language,
        use_llm=not args.no_llm,
        confirm_transcription=False,
        elevenlabs_voice=args.voice,
    )

    print(f"\n Configuration:")
    print(f"   Client: {args.client or '[ask via voice]'}")
    print(f"   Industry: {args.industry or '[ask via voice]'}")
    print(f"   Whisper Model: {args.model}")
    print(f"   Language: {args.language}")
    print(f"   LLM Enhanced: {not args.no_llm}")
    print(f"   Voice: {args.voice or 'auto (rachel if ElevenLabs, system default otherwise)'}")
    print()

    try:
        agent = VoiceInterviewAgent(
            client_name=args.client,
            industry=args.industry,
            config=config,
            output_dir=args.output
        )

        print("\n" + "="*60)
        print("STARTING VOICE INTERVIEW")
        print("="*60)
        print("\nVoice Commands:")
        print("  - Say 'skip' to skip a question")
        print("  - Say 'pause' to pause the interview")
        print("  - Ctrl+C to exit")
        print("="*60 + "\n")

        agent.run_interview()

    except KeyboardInterrupt:
        print("\n\n⏹️ Interview interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
