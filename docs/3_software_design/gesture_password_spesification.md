
# NEXUS Gesture Password Specification

## 1. Purpose

This document defines the hand gesture used as the password for activating and deactivating NEXUS.

---

## 2. Password Gesture

The NEXUS password is an **open-palm hand gesture**:

> 🖐🏻

The gesture consists of:

* One hand
* Palm facing the camera
* Five fingers extended
* Fingers visibly separated or sufficiently distinguishable
* Hand visible within the camera frame

---

## 3. Gesture Recognition

The gesture recognition system shall determine whether the detected hand matches the open-palm password.

Conceptually:

```text
Camera Frame
     ↓
Hand Detection
     ↓
Hand Landmark Extraction
     ↓
Gesture Classification
     ↓
OPEN PALM?
   ├── YES → Valid Password
   └── NO  → Invalid Gesture
```

A confidence threshold shall be used to reduce false detections.

The gesture should be confirmed across multiple consecutive frames rather than accepting a single-frame detection.

---

## 4. Gesture-Person Association

The password must be associated with a tracked person.

```text
Open Palm
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

When NEXUS is in `OFF`:

```text
Valid Open Palm
      ↓
Identify Person
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

When NEXUS is in `FOLLOW`:

```text
Valid Open Palm
      ↓
Identify Person
      ↓
Compare with target_id
      │
      ├── Same person → Deactivate
      │
      └── Different person → Ignore
```

Only the currently locked target can deactivate NEXUS.

---

## 7. False Trigger Prevention

The implementation should include:

* Minimum gesture confidence
* Multi-frame confirmation
* Gesture detection cooldown
* Hand-person association validation
* Rejection of ambiguous hand detections

A single accidental open-palm detection should not immediately trigger repeated activation or deactivation events.

---

## 8. Password Definition Summary

| Parameter          | Specification                                    |
| ------------------ | ------------------------------------------------ |
| Gesture            | 🖐🏻 Open palm                                   |
| Hand count         | One                                              |
| Palm orientation   | Facing camera                                    |
| Fingers            | Five extended                                    |
| Recognition        | Multi-frame confirmation                         |
| Activation         | Valid gesture while`OFF`                       |
| Deactivation       | Valid gesture from`target_id` while `FOLLOW` |
| Other person       | Gesture ignored during`FOLLOW`                 |
| Recognition output | Valid/invalid + associated`track_id`           |

---

## 9. Implementation Principle

The password system follows:

```text
OPEN PALM
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
