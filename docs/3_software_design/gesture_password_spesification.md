
# NEXUS Gesture Password Specification

## 1. Purpose

This document defines the hand gesture used as the password for activating and deactivating NEXUS.

---

## 2. Password Gesture

The official NEXUS password is the **Victory / Peace Sign hand gesture**:

> ✌️

The gesture consists of:

* One hand raised facing the camera
* **Index** and **Middle** fingers extended upward in a 'V' shape
* **Ring** and **Pinky** fingers folded / curled down
* Thumb tucked across ring finger or resting inward
* Hand clearly visible within the camera frame

> [!NOTE]
> **Mengapa Mengganti Telapak Tangan Terbuka (🖐️) ke Victory Sign (✌️)?**
> Gestur telapak tangan terbuka (*Open Palm*) sering mengalami *bias / false positive* karena orang secara alami sering membuka telapak tangan saat berjalan santai, membawa barang, atau sekadar mengayunkan tangan. Gestur **Victory Sign (✌️)** memerlukan tindakan sengaja (*deliberate action*), didukung secara native oleh MediaPipe Tasks Classifier (`Victory`), serta mudah diverifikasi melalui 21 titik koordinat 3D (*landmark*).

---

## 3. Gesture Recognition

The gesture recognition system shall determine whether the detected hand matches the Victory Sign password.

Conceptually:

```text
Camera Frame
     ↓
Hand Detection
     ↓
21 3D Hand Landmark Extraction
     ↓
Gesture Classification (MediaPipe Tasks 'Victory' / Landmark V-Rule)
     ↓
VICTORY SIGN (✌️)?
   ├── YES (Index & Mid Extended, Ring & Pinky Folded) → Valid Password
   └── NO  (Open Palm 🖐️, Fist ✊, Pointing, etc.)   → Ignored
```

A confidence threshold is used to prevent false detections.
The gesture is confirmed across multiple consecutive frames (2 frames) and protected by a 3.0-second cooldown period.

---

## 4. Gesture-Person Association

The password must be associated with a tracked person.

```text
Victory Sign ✌️
    ↓
Identify Hand
    ↓
Associate Hand with Person
    ↓
Get Person Track ID
    ↓
Authentication
```

The gesture alone is not sufficient; the system must determine **which tracked person performed the gesture**.

---

## 5. Activation Rule

When NEXUS is in `OFF` or `GREETING`:

```text
Valid Victory Sign ✌️
      ↓
Identify Person Candidate
      ↓
Authentication SUCCESS
      ↓
Lock Person Track ID
      ↓
TARGET_LOCK
      ↓
FOLLOW
```

The person who performs the valid password becomes the target.

---

## 6. Deactivation Rule

When NEXUS is in `FOLLOW` (`ON`):

```text
Valid Victory Sign ✌️
      ↓
Identify Person
      ↓
Compare with locked target_id
      │
      ├── Same person → Deactivate
      │
      └── Different person → Ignore
```

Only the currently locked target can deactivate NEXUS.

---

## 7. False Trigger Prevention

The implementation includes:

* Dual-layer gesture verification (MediaPipe Deep Classifier + Strict 21-Landmark checks)
* Ring & Pinky curled confirmation (instantly rejects Open Palm 🖐️)
* Face & upper-body exclusion zones (prevents face contours being mistaken for hands)
* Multi-frame confirmation (2 consecutive frames)
* Gesture detection cooldown (3.0 seconds)
* Hand-person association validation
* Rejection of ambiguous hand detections

A single accidental hand motion or waving gesture will not trigger activation or deactivation events.

---

## 8. Password Definition Summary

| Parameter          | Specification                                    |
| ------------------ | ------------------------------------------------ |
| Gesture            | ✌️ Victory / Peace Sign                         |
| Hand count         | One                                              |
| Palm orientation   | Facing camera                                    |
| Extended fingers   | Index & Middle extended, Ring & Pinky folded     |
| Recognition model  | MediaPipe Tasks AI (`Victory`) + 21 Landmark V-Rule |
| Recognition        | Multi-frame confirmation (2 frames)              |
| Activation         | Valid gesture while `OFF` / `GREETING`           |
| Deactivation       | Valid gesture from `target_id` while `FOLLOW`    |
| Other person       | Gesture ignored during `FOLLOW`                  |
| Recognition output | Valid/invalid + associated `track_id`            |

---

## 9. Implementation Principle

The password system follows:

```text
VICTORY SIGN ✌️
    ↓
GESTURE RECOGNITION
    ↓
PERSON ASSOCIATION
    ↓
AUTHENTICATION
    ↓
STATE-DEPENDENT ACTION
```

The **gesture definition belongs to this document**, while the detailed implementation of gesture recognition belongs to the software module specification.
