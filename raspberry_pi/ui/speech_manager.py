#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — Speech & Audio Subsystem (JARVIS Voice)
=====================================================================
File: raspberry_pi/ui/speech_manager.py
Adheres to:
- docs/display_and_greets/greet.md (Sections 1, 2, 3)
- docs/2_system_design/state_machine.md
- docs/5_validation/acceptance_criteria.md (AC-004)

Responsibility:
    Provides asynchronous, non-blocking audio playback for NEXUS robot
    dialogue using pre-rendered British English (JARVIS AI character) audio files.
    Ensures audio playback never blocks the 30 FPS camera loop or tracking pipeline.
"""

from enum import Enum
from pathlib import Path
import shutil
import subprocess
import threading
import time
from typing import Dict, Optional, Callable


class VoiceEvent(Enum):
    """
    Standard voice events defined in docs/display_and_greets/greet.md.
    """
    STARTUP_GREETING = "startup_greeting"
    ACTIVATION = "activation"
    TARGET_LOCKED = "target_locked"
    FOLLOWING = "following"
    TARGET_LOST = "target_lost"
    TARGET_TIMEOUT = "target_timeout"
    DEACTIVATION = "deactivation"
    SYSTEM_ERROR = "system_error"


# Official NEXUS Voice Scripts & File Mapping (JARVIS Character)
VOICE_SCRIPTS: Dict[VoiceEvent, Dict[str, str]] = {
    VoiceEvent.STARTUP_GREETING: {
        "filename": "greet_startup.wav",
        "text": "Welcome to the Technology and Information Department of Brawijaya University! Hello! I’m NEXUS. I’m ready to follow you. Please show me the password.",
        "short_desc": "Startup Greeting (Visitor Welcome)"
    },
    VoiceEvent.ACTIVATION: {
        "filename": "greet_activation.wav",
        "text": "Hello! Nice to see you.",
        "short_desc": "Password Accepted / Activation"
    },
    VoiceEvent.TARGET_LOCKED: {
        "filename": "greet_target_locked.wav",
        "text": "I’ll follow you.",
        "short_desc": "Target Locked"
    },
    VoiceEvent.FOLLOWING: {
        "filename": "greet_following.wav",
        "text": "I’m right behind you.",
        "short_desc": "Following Check-in"
    },
    VoiceEvent.TARGET_LOST: {
        "filename": "greet_target_lost.wav",
        "text": "Where are you?",
        "short_desc": "Target Lost (<3.0s)"
    },
    VoiceEvent.TARGET_TIMEOUT: {
        "filename": "greet_target_timeout.wav",
        "text": "I can’t find you.",
        "short_desc": "Target Lost Timeout -> OFF"
    },
    VoiceEvent.DEACTIVATION: {
        "filename": "greet_deactivation.wav",
        "text": "Okay! See you later!",
        "short_desc": "Deactivation Accepted"
    },
    VoiceEvent.SYSTEM_ERROR: {
        "filename": "greet_system_error.wav",
        "text": "Something went wrong.",
        "short_desc": "System Error Warning"
    }
}


class SpeechManager:
    """
    Asynchronous Speech and Voice Dialogue Manager for NEXUS.
    Plays pre-recorded .wav files via native 'aplay' or falls back to offline TTS.
    """

    def __init__(
        self,
        assets_dir: Optional[Path] = None,
        enabled: bool = True
    ):
        """
        Initialize the Speech Manager.

        Args:
            assets_dir: Directory containing pre-rendered .wav files.
                        Defaults to <project_root>/assets/audio.
            enabled: If False, audio hardware playback is muted (simulated only).
        """
        self.enabled = enabled
        if assets_dir is None:
            # Default to project_root/assets/audio
            project_root = Path(__file__).resolve().parent.parent.parent
            self.assets_dir = project_root / "assets" / "audio"
        else:
            self.assets_dir = Path(assets_dir)

        self.assets_dir.mkdir(parents=True, exist_ok=True)

        # Check for system playback utilities
        self.aplay_available = shutil.which("aplay") is not None
        self.espeak_available = shutil.which("espeak") is not None or shutil.which("espeak-ng") is not None
        self.espeak_bin = shutil.which("espeak-ng") or shutil.which("espeak") or "espeak"

        self._current_process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._last_event: Optional[VoiceEvent] = None
        self._is_playing: bool = False

        status_backend = "aplay (ALSA)" if self.aplay_available else ("espeak" if self.espeak_available else "Console Fallback")
        print(f"[SpeechManager] Initialized | Audio Backend: {status_backend} | Assets: {self.assets_dir}")

    @property
    def is_speaking(self) -> bool:
        """True if speech audio is currently playing."""
        with self._lock:
            if self._current_process is not None:
                if self._current_process.poll() is None:
                    return True
                self._current_process = None
                self._is_playing = False
            return self._is_playing

    def play(
        self,
        event: VoiceEvent,
        interrupt: bool = True,
        on_complete: Optional[Callable[[], None]] = None
    ) -> bool:
        """
        Plays the voice dialogue corresponding to the specified VoiceEvent.
        Executes asynchronously in a non-blocking daemon thread.

        Args:
            event: The VoiceEvent enum to play.
            interrupt: If True, cancels any currently playing dialogue.
            on_complete: Optional callback invoked when speech finishes.

        Returns:
            bool: True if playback was initiated.
        """
        if not self.enabled:
            script_info = VOICE_SCRIPTS.get(event, {})
            print(f"[SpeechManager (MUTED)] 🎙️ \"{script_info.get('text', event.value)}\"")
            if on_complete:
                on_complete()
            return True

        if not interrupt and self.is_speaking:
            # Already speaking and interrupt is disallowed
            return False

        if interrupt:
            self.stop()

        worker = threading.Thread(
            target=self._play_worker,
            args=(event, on_complete),
            daemon=True,
            name=f"SpeechWorker-{event.value}"
        )
        worker.start()
        return True

    def _play_worker(
        self,
        event: VoiceEvent,
        on_complete: Optional[Callable[[], None]] = None
    ) -> None:
        """Background thread executing the actual audio playback."""
        script_info = VOICE_SCRIPTS.get(event, {})
        filename = script_info.get("filename", f"{event.value}.wav")
        text = script_info.get("text", "")
        wav_path = self.assets_dir / filename

        print(f"\n[SpeechManager] 🎙️ [{event.name}] \"{text}\"")

        with self._lock:
            self._is_playing = True
            self._last_event = event

        try:
            # Strategy 1: Play pre-rendered high-quality JARVIS .wav file via aplay
            if wav_path.is_file() and self.aplay_available:
                cmd = ["aplay", "-q", str(wav_path)]
                with self._lock:
                    self._current_process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                self._current_process.wait()

            # Strategy 2: Offline TTS via espeak / espeak-ng with British accent
            elif self.espeak_available and text:
                # -v en-gb: British English voice
                # -s 145: Slightly slower, dignified butler cadence
                cmd = [self.espeak_bin, "-v", "en-gb", "-s", "145", text]
                with self._lock:
                    self._current_process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                self._current_process.wait()

            # Strategy 3: Console simulation fallback with simulated speaking duration
            else:
                simulated_duration = max(1.2, len(text.split()) * 0.35)
                time.sleep(simulated_duration)

        except Exception as e:
            print(f"[SpeechManager] Playback warning: {e}")
        finally:
            with self._lock:
                self._is_playing = False
                self._current_process = None

            if on_complete:
                try:
                    on_complete()
                except Exception as e:
                    print(f"[SpeechManager] Callback error: {e}")

    def stop(self) -> None:
        """Immediately stops any currently playing audio."""
        with self._lock:
            if self._current_process is not None:
                try:
                    self._current_process.terminate()
                    self._current_process.kill()
                except Exception:
                    pass
                self._current_process = None
            self._is_playing = False

    # Convenience helper methods
    def speak_greeting(self, on_complete: Optional[Callable[[], None]] = None) -> bool:
        """Plays Startup Greeting (Visitor Welcome)."""
        return self.play(VoiceEvent.STARTUP_GREETING, on_complete=on_complete)

    def speak_activation(self) -> bool:
        """Plays Activation Acceptance: 'Hello! Nice to see you.'"""
        return self.play(VoiceEvent.ACTIVATION, interrupt=True)

    def speak_target_locked(self) -> bool:
        """Plays Target Locked: 'I’ll follow you.'"""
        return self.play(VoiceEvent.TARGET_LOCKED, interrupt=False)

    def speak_following(self) -> bool:
        """Plays Following Check-in: 'I’m right behind you.'"""
        return self.play(VoiceEvent.FOLLOWING, interrupt=False)

    def speak_target_lost(self) -> bool:
        """Plays Target Lost: 'Where are you?'"""
        return self.play(VoiceEvent.TARGET_LOST, interrupt=True)

    def speak_target_timeout(self) -> bool:
        """Plays Target Lost Timeout: 'I can’t find you.'"""
        return self.play(VoiceEvent.TARGET_TIMEOUT, interrupt=True)

    def speak_deactivation(self) -> bool:
        """Plays Deactivation Accepted: 'Okay! See you later!'"""
        return self.play(VoiceEvent.DEACTIVATION, interrupt=True)

    def speak_system_error(self) -> bool:
        """Plays System Error: 'Something went wrong.'"""
        return self.play(VoiceEvent.SYSTEM_ERROR, interrupt=True)
