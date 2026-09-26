#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — Audio Assets Generator
=====================================================
File: scripts/generate_audio_assets.py

Generates the 8 official voice dialogue .wav files for NEXUS as specified in
docs/display_and_greets/greet.md.

Uses the following generation pipeline:
1. edge-tts (High quality neural British JARVIS voice: en-GB-RyanNeural) if installed.
2. espeak / espeak-ng -w output if available on the system.
3. Built-in Python mathematical audio synthesizer fallback (creates futuristic
   melodic robot chime tones so valid .wav files always exist for aplay).

Usage:
    python3 scripts/generate_audio_assets.py
"""

import math
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from raspberry_pi.ui.speech_manager import VOICE_SCRIPTS, VoiceEvent


def synthesize_fallback_wav(filepath: Path, base_freq: float = 440.0, duration: float = 1.0):
    """
    Generates a futuristic multi-tone chime .wav file using Python's built-in wave module.
    Zero external dependencies, 100% standard library.
    """
    sample_rate = 44100
    num_samples = int(sample_rate * duration)

    filepath.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(filepath), "w") as wav_file:
        wav_file.setnchannels(1)        # Mono
        wav_file.setsampwidth(2)       # 16-bit
        wav_file.setframerate(sample_rate)

        for i in range(num_samples):
            t = float(i) / sample_rate
            # Smooth envelope (fade in and fade out)
            env = math.sin(math.pi * t / duration)

            # Futuristic chime: fundamental + second harmonic + fifth
            val = (
                0.60 * math.sin(2.0 * math.pi * base_freq * t) +
                0.25 * math.sin(2.0 * math.pi * (base_freq * 1.5) * t) +
                0.15 * math.sin(2.0 * math.pi * (base_freq * 2.0) * t)
            ) * env

            sample = int(val * 24000.0)
            sample = max(-32767, min(32767, sample))
            wav_file.writeframes(struct.pack("<h", sample))


def generate_all_assets():
    target_dir = PROJECT_ROOT / "assets" / "audio"
    target_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("NEXUS AUDIO ASSET GENERATOR (JARVIS VOICE SCRIPTS)")
    print(f"Target Directory: {target_dir}")
    print("=" * 65)

    espeak_bin = shutil.which("espeak-ng") or shutil.which("espeak")
    edge_tts_bin = shutil.which("edge-tts")

    # Harmonic base frequencies for fallback chimes
    freq_map = {
        VoiceEvent.STARTUP_GREETING: (523.25, 2.0),   # C5 (Bright welcome)
        VoiceEvent.ACTIVATION: (659.25, 1.2),         # E5 (Affirmative)
        VoiceEvent.TARGET_LOCKED: (783.99, 1.0),       # G5 (Confirmed)
        VoiceEvent.FOLLOWING: (587.33, 0.8),           # D5 (Gentle ping)
        VoiceEvent.TARGET_LOST: (440.0, 1.2),          # A4 (Inquiry)
        VoiceEvent.TARGET_TIMEOUT: (349.23, 1.5),      # F4 (Low alert)
        VoiceEvent.DEACTIVATION: (392.0, 1.2),        # G4 (Goodbye)
        VoiceEvent.SYSTEM_ERROR: (220.0, 1.5),         # A3 (Warning)
    }

    for event, info in VOICE_SCRIPTS.items():
        fname = info["filename"]
        text = info["text"]
        out_file = target_dir / fname

        success = False

        # Method 1: edge-tts (Neural British voice: en-GB-RyanNeural)
        if edge_tts_bin:
            try:
                cmd = [edge_tts_bin, "--voice", "en-GB-RyanNeural", "--text", text, "--write-media", str(out_file)]
                res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                if res.returncode == 0 and out_file.exists() and out_file.stat().st_size > 500:
                    print(f"  [✓] {fname:<28} -> Edge-TTS Neural Voice generated.")
                    success = True
            except Exception:
                pass

        # Method 2: espeak / espeak-ng -w output
        if not success and espeak_bin:
            try:
                cmd = [espeak_bin, "-v", "en-gb", "-s", "145", "-w", str(out_file), text]
                res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                if res.returncode == 0 and out_file.exists() and out_file.stat().st_size > 500:
                    print(f"  [✓] {fname:<28} -> espeak British Voice generated.")
                    success = True
            except Exception:
                pass

        # Method 3: Fallback synthesized chime wav
        if not success:
            base_f, dur = freq_map.get(event, (440.0, 1.0))
            synthesize_fallback_wav(out_file, base_freq=base_f, duration=dur)
            print(f"  [✓] {fname:<28} -> Built-in Chime Audio generated ({base_f:.0f} Hz).")

    print("=" * 65)
    print("All 8 NEXUS voice assets generated successfully!")
    print("You can replace any of these .wav files with custom recordings anytime.")
    print("=" * 65)


if __name__ == "__main__":
    generate_all_assets()
