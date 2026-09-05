
# NEXUS — Acceptance Criteria

## 1. Purpose

This document defines the conditions that must be satisfied for the NEXUS robot to be considered functionally acceptable.

The acceptance criteria are derived from the top-level system requirements and define observable pass/fail conditions for the final system.

---

# 2. Acceptance Principle

NEXUS is accepted only when:

1. Core functionality operates correctly.
2. The correct person is authenticated and locked.
3. NEXUS follows only the locked target.
4. Target loss results in a safe stop and deactivation.
5. ESP32 communication failure results in a safe motor stop.
6. HMI and speech correspond to the robot state.
7. No unresolved safety-critical failure exists.

---

# 3. Functional Acceptance Criteria

## AC-001 — System Startup

### Requirement

NEXUS shall initialize correctly after power-on.

### Acceptance Criteria

* Raspberry Pi starts successfully.
* ESP32 starts successfully.
* Camera becomes available.
* Distance sensor becomes available.
* UART communication is established.
* Motor control subsystem is initialized.
* HMI is initialized.
* Robot enters `OFF`.

### Pass Condition

NEXUS reaches `OFF` without a critical initialization error.

---

# 4. AC-002 — Initial State

### Requirement

NEXUS shall not automatically activate or follow a person after startup.

### Acceptance Criteria

After startup:

* Robot state = `OFF`.
* Target ID = `NONE`.
* Wheel command = `STOP`.
* Live camera is displayed.
* No target is automatically selected.

### Pass Condition

NEXUS remains inactive until a valid password is provided.

---

# 5. AC-003 — Person Detection

### Requirement

NEXUS shall detect people in the camera view.

### Acceptance Criteria

A visible person within the usable camera field shall produce a person detection and tracking result under normal operating conditions.

### Pass Condition

The person is detected and assigned a persistent tracking ID.

---

# 6. AC-004 — Greeting

### Requirement

NEXUS shall greet a nearby person.

### Acceptance Criteria

When a person enters the configured greeting range:

NEXUS shall say:

> “Welcome to the Technology and Information Department of Brawijaya University! Hello! I’m NEXUS. I’m ready to follow you. Please show me the password.”

The greeting:

* Occurs only when the greeting condition is satisfied.
* Does not activate the robot.
* Does not cause the robot to follow the person.
* Does not continuously repeat while the same person remains nearby.

### Pass Condition

Greeting occurs correctly while robot remains logically `OFF`.

---

# 7. AC-005 — Password Recognition

### Requirement

NEXUS shall recognize the predefined password gesture.

### Password

**🖐🏻 Open Palm**

### Acceptance Criteria

A valid gesture consists of:

* One hand.
* Palm facing the camera.
* Five fingers extended.
* Sufficient hand visibility.
* Recognition confidence above configured threshold.
* Gesture confirmed across the required number of frames.

### Pass Condition

A valid open palm is recognized as a password event.

---

# 8. AC-006 — Invalid Gesture Rejection

### Requirement

NEXUS shall reject gestures that do not match the password.

### Acceptance Criteria

The following shall not activate the robot:

* Closed fist.
* Pointing.
* Two-finger gesture.
* Random hand movement.
* Insufficient-confidence gesture.
* Gesture without valid person association.

### Pass Condition

Robot remains `OFF`.

---

# 9. AC-007 — Gesture-Person Association

### Requirement

NEXUS shall identify which tracked person performed the password gesture.

### Acceptance Criteria

When multiple people are visible:

* The gesture must be associated with the correct tracked person.
* The associated `track_id` must be returned.
* An ambiguous gesture shall not activate the robot.

### Pass Condition

The correct person is associated with the password gesture.

---

# 10. AC-008 — Target Lock

### Requirement

NEXUS shall lock the person who successfully authenticates.

### Acceptance Criteria

After valid authentication:

```text
Authenticated Person
        ↓
Track ID
        ↓
Target Manager
        ↓
target_id
```

The selected `target_id` shall remain fixed during normal following.

### Pass Condition

NEXUS follows the authenticated person rather than selecting a different person.

---

# 11. AC-009 — Follow Activation

### Requirement

NEXUS shall enter follow mode after successful authentication.

### Acceptance Criteria

State transition:

```text
OFF
 ↓
TARGET_LOCK
 ↓
FOLLOW
```

NEXUS shall say:

> “Hello! Nice to see you.”

and:

> “I’ll follow you.”

### Pass Condition

NEXUS enters `FOLLOW` only after successful authentication and target lock.

---

# 12. AC-010 — Horizontal Target Alignment

### Requirement

NEXUS shall attempt to keep the target near the horizontal center of the camera.

### Acceptance Criteria

The controller shall use:

$$
e_x=x_c-\frac{W}{2}
$$

where:

* \(x_c\) = target center.
* \(W\) = camera image width.

Expected behavior:

* Target left → robot turns left.
* Target right → robot turns right.
* Target near center → angular velocity approaches zero.

### Pass Condition

The robot direction changes consistently with target horizontal position.

---

# 13. AC-011 — Distance Control

### Requirement

NEXUS shall attempt to maintain the configured following distance.

Initial target:

$$
D_{target}=1.5\,m
$$

with an initial tolerance:

$$
\pm0.2\,m
$$

### Expected Behavior

| Target Position      | Robot Response                        |
| -------------------- | ------------------------------------- |
| Too far              | Move forward                          |
| Within desired range | Stop or move slowly                   |
| Too close            | Stop/reduce forward velocity          |
| Extremely close      | Never command unsafe forward movement |

### Pass Condition

Under controlled test conditions, the robot maintains the target within the configured tolerance after transient motion.

---

# 14. AC-012 — Differential Drive

### Requirement

NEXUS shall convert linear/angular commands into left/right wheel commands.

$$
V_L=V-\frac{\omega W}{2}
$$

$$
V_R=V+\frac{\omega W}{2}
$$

### Acceptance Criteria

* Straight movement → approximately equal wheel commands.
* Left correction → appropriate differential wheel speeds.
* Right correction → appropriate differential wheel speeds.
* Rotation → opposite wheel directions when commanded.
* Wheel commands remain within configured safety limits.

### Pass Condition

Wheel commands correspond correctly to the desired robot motion.

---

# 15. AC-013 — Target Persistence

### Requirement

NEXUS shall maintain the same target while the target remains trackable.

### Acceptance Criteria

When another person enters the camera view:

* New person may receive another Track ID.
* `target_id` remains unchanged.
* Follow controller continues using the original target.

### Pass Condition

NEXUS does not switch targets merely because another person becomes more visible.

---

# 16. AC-014 — Password from Non-Target

### Requirement

A non-target person shall not be able to deactivate NEXUS.

### Acceptance Criteria

While in `FOLLOW`:

```text
Gesture Person ID == target_id
        ↓
      YES → Deactivate

Gesture Person ID != target_id
        ↓
      NO → Ignore
```

### Pass Condition

A valid open-palm gesture from another person does not deactivate NEXUS.

---

# 17. AC-015 — Target Deactivation

### Requirement

The locked target shall be able to deactivate NEXUS using the same password gesture.

### Acceptance Criteria

When the locked target performs 🖐🏻:

```text
FOLLOW
 ↓
Valid Password
 ↓
Associated Track ID
 ↓
Track ID == target_id
 ↓
DEACTIVATING
 ↓
OFF
```

NEXUS shall say:

> “Okay! See you later!”

### Pass Condition

The robot stops following and returns to `OFF`.

---

# 18. AC-016 — Temporary Target Loss

### Requirement

NEXUS shall handle temporary target loss without immediately clearing the target.

### Acceptance Criteria

When the target temporarily disappears:

* Loss timer starts.
* Robot enters target-loss handling.
* NEXUS says:

> “Where are you?”

* If target returns before timeout, following resumes.
* Target ID remains unchanged.

### Pass Condition

Short-duration occlusion or temporary tracking loss does not unnecessarily reset authentication.

---

# 19. AC-017 — Target Loss Timeout

### Requirement

NEXUS shall automatically deactivate if the target is lost for longer than the configured timeout.

Initial timeout:

**1–2 seconds**, subject to experimental calibration.

### Acceptance Criteria

After timeout:

```text
Target Lost
    ↓
Timeout
    ↓
Motor STOP
    ↓
Clear target_id
    ↓
OFF
```

NEXUS shall say:

> “I can’t find you.”

NEXUS shall not automatically search for or select another person.

### Pass Condition

The robot stops and requires new authentication.

---

# 20. AC-018 — Motor Safety

### Requirement

The robot shall stop when a safety-critical condition occurs.

### Acceptance Criteria

Motor stop shall occur when:

* Target-loss timeout is reached.
* STOP command is issued.
* Invalid movement command is detected.
* ESP32 communication timeout occurs.
* Critical control error occurs.

### Pass Condition

Both drive motors are commanded to zero.

---

# 21. AC-019 — ESP32 Communication Watchdog

### Requirement

ESP32 shall provide an independent motor safety mechanism.

### Acceptance Criteria

If the ESP32 does not receive a valid command within:

$$
T_{timeout}=0.2\,s
$$

the ESP32 shall:

* Set left motor command to zero.
* Set right motor command to zero.
* Stop both motors.

### Pass Condition

Loss of Raspberry Pi communication results in motor stop without requiring Raspberry Pi intervention.

---

# 22. AC-020 — HMI

### Requirement

The HMI shall represent the current robot state.

| State        | Required HMI         |
| ------------ | -------------------- |
| OFF          | Live camera          |
| GREETING     | Greeting animation   |
| TARGET_LOCK  | Activation animation |
| FOLLOW       | Robot face           |
| Target lost  | Lost/warning face    |
| DEACTIVATING | Goodbye animation    |
| ERROR        | Error screen         |

### Pass Condition

Displayed HMI corresponds to the logical robot state.

---

# 23. AC-021 — Speech

### Requirement

Speech shall provide appropriate feedback without interfering with motor safety.

### Acceptance Criteria

* Speech corresponds to the current event.
* Welcome speech is not repeated continuously.
* Following speech uses a cooldown.
* Target-loss speech occurs once per loss event.
* Speech processing does not block the control loop.
* Motor STOP has higher priority than speech playback.

### Pass Condition

Speech feedback is correct and does not delay safety-critical actions.

---

# 24. AC-022 — Reverse Movement

### Requirement

Initial implementation shall avoid automatic reverse movement.

### Acceptance Criteria

If the target is too close:

* Forward velocity shall be reduced or set to zero.
* NEXUS shall not automatically command reverse movement unless explicitly enabled in a future configuration.

### Pass Condition

No unintended backward motion occurs during normal distance control.

---

# 25. AC-023 — Multi-Person Operation

### Scenario

At least two people are present.

Person A authenticates.

Person B enters the scene.

### Acceptance Criteria

NEXUS shall:

* Lock Person A.
* Continue following Person A.
* Ignore Person B as a target.
* Ignore Person B's password gesture for deactivation.

### Pass Condition

Target identity remains stable.

---

# 26. AC-024 — Complete User Interaction

The complete interaction shall operate as:

```text
POWER ON
   ↓
OFF
   ↓
Person Nearby
   ↓
GREETING
   ↓
OFF
   ↓
🖐🏻 Open Palm
   ↓
TARGET LOCK
   ↓
FOLLOW
   ↓
Target Movement
   ↓
Follow Control
   ↓
Target 🖐🏻
   ↓
DEACTIVATING
   ↓
OFF
```

### Pass Condition

The entire sequence completes without manual intervention except for the user's physical interaction.

---

# 27. AC-025 — Recovery After Target Loss

### Scenario

The target leaves the camera view for longer than the configured timeout.

### Acceptance Criteria

NEXUS shall:

1. Stop the motors.
2. Clear the target ID.
3. Enter `OFF`.
4. Display the live camera.
5. Require a new password for activation.
6. Not automatically select another person.

### Pass Condition

NEXUS returns to a safe authenticated-idle state.

---

# 28. AC-026 — Error Handling

### Requirement

Critical software or hardware errors shall result in a safe state.

### Acceptance Criteria

When a critical error occurs:

* Motor commands become zero.
* Robot enters `ERROR` or another explicitly defined safe state.
* HMI displays the error screen.
* Error is logged.
* Robot does not continue autonomous following.

Speech may provide:

> “Something went wrong.”

### Pass Condition

The system fails safely rather than continuing uncontrolled motion.

---

# 29. Performance Acceptance Criteria

The following initial performance targets shall be verified:

| Parameter              |   Acceptance Target |
| ---------------------- | ------------------: |
| Camera                 | ≥ 25 FPS practical |
| Person detection       |           ≥ 10 FPS |
| Tracking               |           ≥ 20 FPS |
| Gesture recognition    |           ≥ 10 FPS |
| Distance sensing       |            ≥ 10 Hz |
| Follow control         |            ≥ 20 Hz |
| UART command rate      |              ~30 Hz |
| ESP32 watchdog timeout |            ≤ 0.2 s |

These values may be refined after hardware benchmarking.

---

# 30. Safety Acceptance Criteria

All following criteria are mandatory:

### SA-001

Target-loss timeout causes motor stop.

### SA-002

ESP32 communication timeout causes motor stop.

### SA-003

Invalid velocity commands cannot cause uncontrolled movement.

### SA-004

Wheel velocity commands are saturated.

### SA-005

Missing target information cannot generate normal follow commands.

### SA-006

A non-target person cannot deactivate the robot.

### SA-007

Target timeout clears the target ID.

### SA-008

NEXUS does not automatically reacquire a new target after timeout.

### SA-009

Speech cannot prevent or delay a safety-critical motor stop.

### SA-010

Robot starts in an inactive state.

---

# 31. Acceptance Test Summary

The final acceptance test shall confirm:

| Category                   | Acceptance |
| -------------------------- | ---------- |
| Startup                    | PASS       |
| Initial OFF state          | PASS       |
| Person detection           | PASS       |
| Person tracking            | PASS       |
| Greeting                   | PASS       |
| Open-palm recognition      | PASS       |
| Gesture-person association | PASS       |
| Authentication             | PASS       |
| Target lock                | PASS       |
| Follow control             | PASS       |
| Distance control           | PASS       |
| Target persistence         | PASS       |
| Multi-person protection    | PASS       |
| Target deactivation        | PASS       |
| Temporary target loss      | PASS       |
| Target-loss timeout        | PASS       |
| Motor safety               | PASS       |
| ESP32 watchdog             | PASS       |
| HMI                        | PASS       |
| Speech                     | PASS       |
| Error handling             | PASS       |

---

# 32. Final Acceptance Decision

NEXUS is considered **ACCEPTED** when:

* All mandatory acceptance criteria pass.
* All P0 safety tests pass.
* All core P1 functionality passes.
* No unresolved safety-critical defects remain.
* The complete end-to-end interaction succeeds.
* The robot demonstrates predictable and repeatable behavior under controlled test conditions.

If any mandatory safety criterion fails, the system shall be classified as:

**NOT ACCEPTED**

until the failure is corrected and the relevant test is repeated.
