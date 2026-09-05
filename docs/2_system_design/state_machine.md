# NEXUS State Machine

## 1. Purpose

This document defines the behavioral state machine of NEXUS.

The state machine determines:

* What NEXUS does in each operating state
* Which events cause state transitions
* Conditions required for each transition
* Actions performed during transitions
* Motor behavior
* HMI behavior
* Speech behavior
* Target management behavior

The state machine is the primary behavioral specification for the high-level robot software.

---

# 2. State Overview

NEXUS uses the following main states:

```text
OFF
GREETING
TARGET_LOCK
FOLLOW
DEACTIVATING
ERROR
```

The normal operating cycle is:

```text
OFF
 ↓
GREETING
 ↓
OFF
 ↓
TARGET_LOCK
 ↓
FOLLOW
 ↓
DEACTIVATING
 ↓
OFF
```

Target loss provides another path:

```text
FOLLOW
 ↓
Target Lost
 ↓
Loss Timeout
 ↓
OFF
```

---

# 3. State Definitions

## 3.1 OFF

`OFF` is the default waiting state.

Important clarification:

**OFF does not mean the Raspberry Pi or camera is powered down.**

It means that NEXUS is logically inactive and must not follow a person.

### Responsibilities

While `OFF`, NEXUS shall:

* Keep the camera active
* Detect people
* Monitor proximity
* Detect the password gesture
* Display the live camera
* Wait for a nearby person
* Wait for valid authentication
* Ensure no target is locked
* Ensure motors are stopped

### Motor

```text
Left motor  = STOP
Right motor = STOP
```

### HMI

```text
Live camera
```

### Target

```text
target_id = NONE
```

### Speech

No continuous speech.

---

# 4. GREETING

`GREETING` is entered when NEXUS detects a person within the configured greeting range while `OFF`.

The greeting does **not** activate the robot.

### Entry condition

```text
State = OFF
AND
Person detected
AND
Person within GREETING_DISTANCE
AND
Greeting allowed
```

### Actions

NEXUS shall:

1. Play the startup greeting.
2. Display the greeting animation/interface.
3. Keep the motors stopped.
4. Return to `OFF` after the greeting interaction.

### Speech

NEXUS says:

> "Welcome to the Technology and Information Department of Brawijaya University! Hello! I’m NEXUS. I’m ready to follow you. Please show me the password."

### Motor

```text
STOP
```

### Important behavior

Greeting does not mean authentication.

```text
Person nearby
     ↓
GREETING
     ↓
Speech
     ↓
OFF
     ↓
Wait for password
```

---

# 5. TARGET_LOCK

`TARGET_LOCK` is the transition state between successful authentication and active following.

It is responsible for establishing the authenticated person as the target.

### Entry condition

```text
State = OFF
AND
Valid password detected
AND
Gesture successfully associated with a tracked person
```

### Actions

1. Validate the password gesture.
2. Identify the associated tracking ID.
3. Store the tracking ID as `target_id`.
4. Confirm that the target exists.
5. Initialize target tracking information.
6. Prepare the follow controller.
7. Play activation/target-lock speech.
8. Transition to `FOLLOW`.

### Target

Example:

```text
target_id = 7
```

### Speech

Activation:

> "Hello! Nice to see you."

Target lock:

> "I’ll follow you."

### Motor

Motors remain stopped during target initialization unless explicitly determined safe by the control system.

Initial recommended behavior:

```text
TARGET_LOCK
    ↓
Motor STOP
    ↓
Target confirmed
    ↓
FOLLOW
```

---

# 6. FOLLOW

`FOLLOW` is the primary active state.

NEXUS follows only the person associated with `target_id`.

### Responsibilities

While following, NEXUS shall:

* Track the target
* Determine target horizontal position
* Measure target distance
* Calculate horizontal error
* Calculate distance error
* Generate linear velocity
* Generate angular velocity
* Calculate left/right wheel velocities
* Send commands to ESP32
* Monitor target visibility
* Monitor authentication gesture
* Monitor safety conditions

---

# 7. Target Tracking During FOLLOW

The target is identified by its tracking ID.

Example:

```text
target_id = 7
```

If the tracker reports:

```text
Person 2
Person 5
Person 7
Person 9
```

NEXUS uses only:

```text
Person 7
```

for following.

The robot must not automatically switch to Person 2, 5, or 9.

---

# 8. FOLLOW Control

The follow controller receives:

```text
Target horizontal position
Target distance
```

and produces:

```text
V
ω
```

These are converted into wheel commands:

```text
V, ω
 ↓
Differential Drive
 ↓
V_left
V_right
 ↓
UART
 ↓
ESP32
```

---

# 9. Normal FOLLOW Behavior

When the target is visible and at a valid distance:

```text
Target detected
      ↓
Target centered?
      │
      ├── NO → adjust angular velocity
      │
      └── YES
             ↓
      Check distance
             │
       ┌─────┼─────┐
       ▼     ▼     ▼
    Too far  OK  Too close
       │     │      │
       ▼     ▼      ▼
    Forward Slow    Stop
```

---

# 10. Following Speech

The phrase:

> "I’m right behind you."

may be played occasionally while following.

It must use a cooldown mechanism.

It must **not** be played continuously every control cycle.

Example:

```text
FOLLOW
 ↓
Speech cooldown expired?
 ├── NO → continue following
 └── YES
       ↓
"I’m right behind you."
       ↓
Reset cooldown
```

Speech must never block the motor-control loop.

---

# 11. Target Temporarily Lost

If the locked target is temporarily unavailable:

```text
FOLLOW
   ↓
Target not detected
   ↓
Start loss timer
```

NEXUS enters a target-loss handling condition while maintaining the `FOLLOW` state until the timeout decision is made.

### First loss event

NEXUS may say:

> "Where are you?"

This should occur once per loss event.

---

# 12. Target Returns Before Timeout

If the target becomes visible again before the configured timeout:

```text
Target Lost
     ↓
Target detected again
     ↓
Cancel loss timer
     ↓
Continue FOLLOW
```

The same `target_id` must remain locked.

NEXUS must not require a new password for a temporary tracking failure.

---

# 13. Target Lost Beyond Timeout

If the target remains lost beyond the configured timeout:

```text
FOLLOW
   ↓
Target lost
   ↓
Loss timer
   ↓
TIMEOUT
   ↓
Stop motors
   ↓
Clear target
   ↓
OFF
```

Initial timeout:

```text
~1–2 seconds
```

The exact value must be experimentally calibrated.

### Actions

1. Immediately stop the motors.
2. Clear the target ID.
3. Stop follow control.
4. Reset target tracking state.
5. Return to `OFF`.
6. Display the live camera.
7. Require a new valid password for activation.

### Speech

> "I can’t find you."

### Important restriction

NEXUS must **not** automatically search for or lock another person after timeout.

---

# 14. Valid Password During FOLLOW

The same password gesture can deactivate NEXUS.

However, the gesture must come from the currently locked target.

```text
Password detected
      ↓
Is gesture valid?
      ↓
YES
      ↓
Identify person
      ↓
Is person == target_id?
      │
      ├── YES → DEACTIVATING
      │
      └── NO  → Ignore
```

---

# 15. Invalid Password During FOLLOW

If the gesture is invalid:

```text
Invalid gesture
     ↓
Ignore
     ↓
Continue FOLLOW
```

No state transition occurs.

---

# 16. Password From Another Person

If another person performs the valid gesture:

```text
Person A = target
Person B = other person

Person B shows valid password
             ↓
      Gesture recognized
             ↓
      Associated with B
             ↓
       B != target_id
             ↓
          IGNORE
             ↓
        Continue FOLLOW
```

This prevents unauthorized deactivation.

---

# 17. DEACTIVATING

`DEACTIVATING` is a short transition state used when the currently locked target provides a valid deactivation gesture.

### Entry condition

```text
State = FOLLOW
AND
Valid password detected
AND
Gesture belongs to target_id
```

### Actions

1. Stop the robot.
2. Clear target ID.
3. Stop follow control.
4. Play goodbye speech.
5. Display deactivation animation.
6. Return to `OFF`.

### Speech

> "Okay! See you later!"

### Motor

```text
STOP
```

---

# 18. ERROR

`ERROR` is an optional state for unrecoverable or critical system errors.

Possible causes:

* Camera failure
* Critical software failure
* Sensor failure
* Communication failure
* Invalid internal state
* Motor-control fault

### Actions

```text
ERROR
 ↓
STOP MOTORS
 ↓
Display error screen
 ↓
Log error
 ↓
Speech
```

### Speech

> "Something went wrong."

The exact recovery mechanism depends on the type of error.

---

# 19. Complete State Transition Diagram

```text
                         ┌─────────────────────┐
                         │         OFF         │
                         │                     │
                         │ Motors: STOP        │
                         │ HMI: Live Camera    │
                         │ Target: NONE        │
                         └──────────┬──────────┘
                                    │
                        person nearby
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │      GREETING       │
                         │                     │
                         │ Motors: STOP        │
                         │ HMI: Greeting       │
                         │ Speech: Welcome     │
                         └──────────┬──────────┘
                                    │
                              greeting done
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │         OFF         │
                         └──────────┬──────────┘
                                    │
                            valid password
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    TARGET_LOCK      │
                         │                     │
                         │ Lock target ID      │
                         │ Motors: STOP        │
                         └──────────┬──────────┘
                                    │
                              target locked
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │       FOLLOW       │
                         │                     │
                         │ Track target        │
                         │ Control motors       │
                         │ HMI: Robot Face     │
                         └──────┬───────┬──────┘
                                │       │
             target returns     │       │ target lost
                                │       ▼
                                │   Loss Timer
                                │       │
                                │       ├── returns
                                │       │      │
                                │       │      └──► FOLLOW
                                │       │
                                │       └── timeout
                                │              │
                                │              ▼
                                │             OFF
                                │
                      valid password
                      from target
                                │
                                ▼
                     ┌─────────────────────┐
                     │    DEACTIVATING     │
                     │                     │
                     │ Motors: STOP        │
                     │ Goodbye speech      │
                     └──────────┬──────────┘
                                │
                         deactivation done
                                │
                                ▼
                              OFF
```

---

# 20. State Transition Table

| Current State | Trigger               | Condition                              | Action                | Next State   |
| ------------- | --------------------- | -------------------------------------- | --------------------- | ------------ |
| OFF           | Person detected       | Within greeting range                  | Start greeting        | GREETING     |
| OFF           | Greeting completed    | —                                      | Resume monitoring     | OFF          |
| OFF           | Valid password        | Gesture associated with tracked person | Lock target           | TARGET_LOCK  |
| GREETING      | Greeting completed    | —                                      | Stop speech/animation | OFF          |
| TARGET_LOCK   | Target confirmed      | Valid target ID                        | Initialize following  | FOLLOW       |
| TARGET_LOCK   | Target invalid        | Cannot identify target                 | Clear authentication  | OFF          |
| FOLLOW        | Target visible        | Normal tracking                        | Follow target         | FOLLOW       |
| FOLLOW        | Target lost           | Within timeout                         | Start loss timer      | FOLLOW       |
| FOLLOW        | Target returns        | Before timeout                         | Resume tracking       | FOLLOW       |
| FOLLOW        | Target lost           | Timeout exceeded                       | Stop, clear target    | OFF          |
| FOLLOW        | Valid password        | Gesture belongs to target              | Stop and deactivate   | DEACTIVATING |
| FOLLOW        | Valid password        | Gesture belongs to another person      | Ignore                | FOLLOW       |
| FOLLOW        | Invalid gesture       | —                                      | Ignore                | FOLLOW       |
| DEACTIVATING  | Deactivation complete | —                                      | Clear state           | OFF          |
| Any state     | Critical error        | —                                      | Stop motors           | ERROR        |
| ERROR         | Recovery/reset        | System healthy                         | Reinitialize          | OFF          |

---

# 21. State Entry and Exit Actions

## OFF

### Entry

```text
Motor STOP
Clear target
Enable live camera
Reset follow controller
Enable authentication monitoring
```

### Exit

Depends on destination.

---

## GREETING

### Entry

```text
Display greeting
Play welcome speech
Motor STOP
```

### Exit

```text
Stop greeting animation
Stop/finish speech
Return to monitoring
```

---

## TARGET_LOCK

### Entry

```text
Validate authenticated person
Store target_id
Motor STOP
Display activation state
```

### Exit

```text
Initialize follow controller
```

---

## FOLLOW

### Entry

```text
Display robot face
Initialize target tracking
Enable follow controller
```

### Exit

```text
Stop follow controller
Stop motors
```

---

## DEACTIVATING

### Entry

```text
Motor STOP
Clear target
Display goodbye animation
Play goodbye speech
```

### Exit

```text
Return to OFF
Enable live camera
```

---

## ERROR

### Entry

```text
Motor STOP
Log error
Display error state
Play error speech
```

---

# 22. Authentication Rules

Authentication behavior depends on the current state.

## OFF

```text
Valid password
+
Associated tracked person
        ↓
Accept
        ↓
Lock person
        ↓
TARGET_LOCK
```

## FOLLOW

```text
Valid password
+
Gesture belongs to target
        ↓
Accept
        ↓
DEACTIVATING
```

## FOLLOW — Other Person

```text
Valid password
+
Gesture belongs to another person
        ↓
Reject
        ↓
FOLLOW
```

---

# 23. Greeting Rules

Greeting is independent from authentication.

A nearby person causes:

```text
OFF
 ↓
GREETING
 ↓
Welcome speech
 ↓
OFF
```

It does **not** cause:

```text
Person nearby
 ↓
FOLLOW
```

Activation always requires the password gesture.

The greeting should not repeatedly trigger while the same person remains within greeting range.

A greeting cooldown or interaction flag must prevent repeated greetings.

The greeting permission is reset when the person leaves the greeting range.

---

# 24. Motor Safety Rules

The following states must have motors stopped:

```text
OFF
GREETING
TARGET_LOCK
DEACTIVATING
ERROR
```

The `FOLLOW` state is the only normal state in which movement commands are generated.

Additionally:

```text
UART communication timeout
        ↓
ESP32 STOP
```

This provides a second layer of motor safety independent of the Raspberry Pi state machine.

---

# 25. State Machine Invariants

The following conditions must always be true.

### Invariant 1 — No target while OFF

```text
state == OFF
→ target_id == NONE
```

### Invariant 2 — No movement outside FOLLOW

```text
state != FOLLOW
→ commanded_velocity == 0
```

### Invariant 3 — Only target can deactivate

```text
deactivation gesture
→ gesture_person_id == target_id
```

### Invariant 4 — Target timeout clears target

```text
target lost beyond timeout
→ target_id == NONE
```

### Invariant 5 — No automatic reacquisition

```text
target timeout
→ OFF
→ require new authentication
```

### Invariant 6 — ESP32 remains responsible for final motor safety

```text
Pi command unavailable
→ ESP32 timeout
→ motors STOP
```

---

# 26. Recommended State Machine Implementation

The state machine should be implemented as an explicit state representation rather than relying on scattered Boolean variables.

Conceptually:

```text
RobotState
├── OFF
├── GREETING
├── TARGET_LOCK
├── FOLLOW
├── DEACTIVATING
└── ERROR
```

The high-level controller should process:

```text
Current State
      +
Events
      +
Sensor/Perception Data
      ↓
State Transition Logic
      ↓
Next State
      +
State Actions
```

This architecture should eventually be implemented primarily through `state.py` and coordinated by `main.py`.

---

# 27. State Machine Summary

The fundamental NEXUS behavior is:

```text
POWER ON
   ↓
Initialize
   ↓
OFF
   │
   ├── Person nearby
   │       ↓
   │    GREETING
   │       ↓
   │      OFF
   │
   └── Valid password
           ↓
      TARGET_LOCK
           ↓
         FOLLOW
           │
           ├── Target visible
           │       ↓
           │     FOLLOW
           │
           ├── Target temporarily lost
           │       ↓
           │   Target returns
           │       ↓
           │     FOLLOW
           │
           ├── Target lost too long
           │       ↓
           │      OFF
           │
           └── Target gives valid password
                   ↓
              DEACTIVATING
                   ↓
                  OFF
```

The key behavioral principle is:

> **NEXUS only follows an authenticated, explicitly locked target and only the locked target can deactivate the robot using the password gesture.**
