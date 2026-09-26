#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — Greeting & Speech Subsystem Test
==============================================================
File: scripts/test_greeting_speech.py

Tests:
1. SpeechManager audio playback for all 8 VoiceEvents (non-blocking).
2. GreetingManager 3-layer anti-spam logic simulation.

Usage:
    # 1. Test all voice events in sequence
    python3 scripts/test_greeting_speech.py --test-speech

    # 2. Test specific voice event
    python3 scripts/test_greeting_speech.py --event startup_greeting

    # 3. Test 3-layer anti-spam logic simulation
    python3 scripts/test_greeting_speech.py --test-anti-spam
"""

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from raspberry_pi.ui.speech_manager import SpeechManager, VoiceEvent, VOICE_SCRIPTS
from raspberry_pi.ui.greeting_manager import GreetingManager


@dataclass
class MockTrack:
    track_id: int


def test_speech_playback(event_name: str = "all"):
    print("=" * 65)
    print("NEXUS SPEECH MANAGER — AUDIO PLAYBACK TEST")
    print("=" * 65)

    speech = SpeechManager()

    if event_name != "all":
        try:
            ev = VoiceEvent(event_name)
            events_to_test = [ev]
        except ValueError:
            print(f"[ERROR] Unknown voice event '{event_name}'. Available events:")
            for e in VoiceEvent:
                print(f"  - {e.value}")
            return
    else:
        events_to_test = list(VoiceEvent)

    for ev in events_to_test:
        info = VOICE_SCRIPTS[ev]
        print(f"\n▶ Testing Event: {ev.name} ({info['short_desc']})")
        print(f"  File : {info['filename']}")
        print(f"  Text : \"{info['text']}\"")

        speech.play(ev, interrupt=True)

        # Wait while speaking
        while speech.is_speaking:
            time.sleep(0.05)

        print("  [✓] Playback complete.")
        time.sleep(0.5)

    print("\n" + "=" * 65)
    print("Speech Manager Playback Test PASSED!")
    print("=" * 65)


def test_anti_spam_logic():
    print("=" * 65)
    print("NEXUS GREETING MANAGER — 3-LAYER ANTI-SPAM SIMULATION")
    print("=" * 65)

    # Cooldown 3s, empty reset 2s for fast unit testing
    gm = GreetingManager(cooldown_seconds=3.0, empty_reset_seconds=2.0)

    # Test Step 1: Initial state (scene empty)
    should, cand = gm.evaluate(tracks=[], is_off_state=True)
    assert not should, "Empty scene should not trigger greeting"
    print("✓ Test 1: Empty scene -> No greeting.")

    # Test Step 2: Person #1 appears -> Must trigger greeting!
    tracks = [MockTrack(track_id=1)]
    should, cand = gm.evaluate(tracks=tracks, is_off_state=True)
    assert should and cand == 1, "Person #1 should trigger greeting"
    gm.mark_greeted(1)
    print("✓ Test 2: Person #1 enters -> Greeting TRIGGERED.")

    # Test Step 3: Person #1 remains -> Layer 1 (Track-ID Latch) MUST block repeated greeting!
    should, cand = gm.evaluate(tracks=tracks, is_off_state=True)
    assert not should, "Person #1 still in front of robot must NOT trigger repeated greeting"
    print("✓ Test 3: Person #1 still present -> Layer 1 BLOCKED repeated greeting.")

    # Test Step 4: Person #2 appears alongside Person #1 -> Cooldown (Layer 3) active
    tracks_two = [MockTrack(track_id=2), MockTrack(track_id=1)]
    should, cand = gm.evaluate(tracks=tracks_two, is_off_state=True)
    assert not should, "Layer 3 Cooldown should prevent instant second greeting"
    print("✓ Test 4: Person #2 appears during cooldown -> Layer 3 Cooldown active.")

    # Test Step 5: Wait for cooldown to expire
    print("  Waiting 3.2s for cooldown...")
    time.sleep(3.2)
    should, cand = gm.evaluate(tracks=tracks_two, is_off_state=True)
    assert should and cand == 2, "Person #2 should now trigger greeting after cooldown"
    gm.mark_greeted(2)
    print("✓ Test 5: Person #2 greeting TRIGGERED after cooldown.")

    # Test Step 6: Both leave -> Scene empty for 1s (less than 2s threshold) -> Should NOT reset yet
    gm.evaluate(tracks=[], is_off_state=True)
    time.sleep(1.0)
    gm.evaluate(tracks=[], is_off_state=True)
    # Person #1 returns briefly
    should, cand = gm.evaluate(tracks=[MockTrack(track_id=1)], is_off_state=True)
    assert not should, "Person #1 returning before empty timeout should still be blocked"
    print("✓ Test 6: Brief exit (<2s) did NOT reset Person #1 latch.")

    # Test Step 7: Scene empty for > 2s -> Layer 2 resets greeted memory!
    print("  Scene empty for 2.2s...")
    gm.evaluate(tracks=[], is_off_state=True)
    time.sleep(2.2)
    gm.evaluate(tracks=[], is_off_state=True)

    # Now Person #1 returns as a new visitor interaction
    should, cand = gm.evaluate(tracks=[MockTrack(track_id=1)], is_off_state=True)
    assert should and cand == 1, "Memory should have been reset; Person #1 should be greeted again"
    gm.mark_greeted(1)
    print("✓ Test 7: Scene empty >= 2s -> Layer 2 RESET memory, new visit greeted!")

    print("\n" + "=" * 65)
    print("All 3-Layer Anti-Spam tests PASSED successfully!")
    print("=" * 65)


def test_deactivation_scene_clear():
    print("=" * 65)
    print("NEXUS GREETING MANAGER — DEACTIVATION SCENE CLEAR TEST")
    print("=" * 65)

    gm = GreetingManager(cooldown_seconds=15.0, empty_reset_seconds=5.0)

    # 1. Simulate deactivation
    gm.on_deactivation()
    assert gm.require_scene_clear, "require_scene_clear must be True on deactivation"
    print("✓ Step 1: Deactivation latch activated (require_scene_clear = True).")

    # 2. Person remains in front of robot -> MUST BE BLOCKED
    tracks = [MockTrack(track_id=1)]
    should, _ = gm.evaluate(tracks=tracks, is_off_state=True, is_speaking=False)
    assert not should, "Greeting must be BLOCKED while scene is not cleared after deactivation"
    print("✓ Step 2: Person still in frame -> Greeting strictly BLOCKED.")

    # 3. Audio speaking active -> MUST BE BLOCKED
    should, _ = gm.evaluate(tracks=tracks, is_off_state=True, is_speaking=True)
    assert not should, "Greeting must be BLOCKED while audio is speaking"
    print("✓ Step 3: Audio speaking active -> Greeting BLOCKED.")

    # 4. Scene clear for 0.8s (<1.5s) -> Still not reset
    gm.evaluate(tracks=[], is_off_state=True)
    time.sleep(0.8)
    gm.evaluate(tracks=[], is_off_state=True)
    assert gm.require_scene_clear, "Scene clear < 1.5s must NOT reset latch"
    print("✓ Step 4: Scene clear < 1.5s -> Latch maintained.")

    # 5. Scene clear for > 1.5s -> Reset latch!
    time.sleep(0.8)  # total 1.6s empty
    gm.evaluate(tracks=[], is_off_state=True)
    assert not gm.require_scene_clear, "Scene clear >= 1.5s must reset latch"
    print("✓ Step 5: Scene clear >= 1.5s -> Latch reset (ready for new visitor)!")

    # 6. New visitor enters -> Greeting triggers!
    should, cand = gm.evaluate(tracks=[MockTrack(track_id=2)], is_off_state=True)
    assert should and cand == 2, "New visitor must trigger greeting after scene cleared"
    print("✓ Step 6: New visitor enters -> Greeting successfully TRIGGERED.")

    print("\n" + "=" * 65)
    print("Deactivation Scene Clear Test PASSED!")
    print("=" * 65)


def test_target_recovery():
    print("=" * 65)
    print("NEXUS TARGET LOCK MANAGER — RE-ACQUISITION TEST")
    print("=" * 65)

    from raspberry_pi.target.locking_target import TargetLockManager, PersonDetection, TargetStatus, TargetEvent

    target_mgr = TargetLockManager(loss_timeout_seconds=4.0)

    # 1. Lock onto person #1
    p1 = MockTrack(track_id=1)
    target_mgr.lock_target(1, p1)
    assert target_mgr.status == TargetStatus.LOCKED
    print("✓ Step 1: Target #1 locked.")

    # 2. Target lost (person disappears)
    _, ev = target_mgr.update(tracks=[])
    assert ev == TargetEvent.TARGET_LOST
    assert target_mgr.status == TargetStatus.LOST
    print("✓ Step 2: Target lost event emitted, status set to LOST.")

    # 3. Simulate missing for 1.5s (<4.0s)
    for _ in range(5):
        _, ev = target_mgr.update(tracks=[])
        assert ev == TargetEvent.NONE
        assert target_mgr.status == TargetStatus.LOST
    print("✓ Step 3: Target continues in LOST state during grace period.")

    # 4. Target returns before 4.0s timeout with new track ID #2
    p2 = MockTrack(track_id=2)
    _, ev = target_mgr.update(tracks=[p2])
    assert ev == TargetEvent.TARGET_REACQUIRED, f"Expected TARGET_REACQUIRED, got {ev}"
    assert target_mgr.status == TargetStatus.LOCKED
    assert target_mgr.locked_target_id == 2
    print(f"✓ Step 4: Target REACQUIRED as ID #{target_mgr.locked_target_id} before timeout!")

    print("\n" + "=" * 65)
    print("Target Recovery Test PASSED!")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="NEXUS Greeting & Speech Subsystem Test")
    parser.add_argument("--test-speech", action="store_true", help="Test all 8 voice events playback")
    parser.add_argument("--event", type=str, default=None, help="Test a specific voice event")
    parser.add_argument("--test-anti-spam", action="store_true", help="Run 3-layer anti-spam unit test")
    parser.add_argument("--test-deactivation-clear", action="store_true", help="Run deactivation scene-clear unit test")
    parser.add_argument("--test-recovery", action="store_true", help="Run target recovery / reacquisition unit test")

    args = parser.parse_args()

    if args.test_anti_spam:
        test_anti_spam_logic()
    elif args.test_deactivation_clear:
        test_deactivation_scene_clear()
    elif args.test_recovery:
        test_target_recovery()
    elif args.event:
        test_speech_playback(args.event)
    else:
        # Default: run logic tests
        test_anti_spam_logic()
        print("\n")
        test_deactivation_scene_clear()
        print("\n")
        test_target_recovery()


if __name__ == "__main__":
    main()
