
# NEXUS — Test Plan

## 1. Purpose

This document defines the verification and validation strategy for the NEXUS mobile human-following robot.

The purpose of testing is to verify that:

* Each subsystem operates according to its specification.
* Raspberry Pi and ESP32 communicate correctly.
* The robot correctly recognizes and authenticates the password gesture.
* NEXUS locks the correct person as its target.
* NEXUS follows only the locked target.
* The robot maintains the desired target distance and horizontal alignment.
* Target loss is handled safely.
* The robot automatically stops when required.
* HMI and speech behavior correspond to the robot state.
* The complete system satisfies the top-level requirements.

---

# 2. Testing Strategy

Testing is divided into several levels:

```text
Unit Test
    ↓
Module Test
    ↓
Subsystem Test
    ↓
Interface Test
    ↓
Integration Test
    ↓
System Test
    ↓
Acceptance Test
```

Each level verifies a different aspect of the system.

| Test Level       | Objective                             |
| ---------------- | ------------------------------------- |
| Unit Test        | Verify individual functions           |
| Module Test      | Verify individual software modules    |
| Subsystem Test   | Verify groups of related modules      |
| Interface Test   | Verify communication between modules  |
| Integration Test | Verify interaction between subsystems |
| System Test      | Verify complete robot behavior        |
| Acceptance Test  | Verify top-level requirements         |

---

# 3. Test Environment

## 3.1 Hardware

The minimum test hardware consists of:

* Raspberry Pi 5
* Camera
* Distance sensor
* Monitor/display
* Speaker
* ESP32
* Left DC geared motor
* Right DC geared motor
* Left wheel encoder
* Right wheel encoder
* Motor driver
* Battery/power system
* 1 passive front caster wheel
* 2 rear motorized wheels

Mechanical configuration:

```text
             Front
               ↑
               ○
          Passive Caster
             
        ┌─────────────┐
        │   NEXUS     │
        │             │
        └─────────────┘
          O         O
       Left Rear  Right Rear
        Motor       Motor
```

---

## 3.2 Software

The test environment should include:

* Raspberry Pi OS
* Python environment
* OpenCV
* Person detection model
* Person tracking algorithm
* Gesture recognition framework
* UART communication software
* ESP32 firmware
* HMI software
* Speech system
* Logging system

---

# 4. Test Classification

Each test is assigned a priority.

| Priority | Meaning                  |
| -------- | ------------------------ |
| P0       | Safety-critical          |
| P1       | Core functionality       |
| P2       | Supporting functionality |
| P3       | Optional/non-critical    |

P0 tests must pass before the robot is allowed to operate autonomously.

---

# 5. Unit Tests

## 5.1 Center Controller

### Objective

Verify that the center controller generates the correct angular command based on target position.

### Test Cases

| ID        | Input                          | Expected Result                 |
| --------- | ------------------------------ | ------------------------------- |
| TC-CC-001 | Target exactly at image center | Angular velocity ≈ 0           |
| TC-CC-002 | Target left of center          | Robot commands left correction  |
| TC-CC-003 | Target right of center         | Robot commands right correction |
| TC-CC-004 | Extremely large error          | Angular velocity is saturated   |
| TC-CC-005 | Invalid target position        | No movement command             |

---

# 6. Distance Controller Tests

### Objective

Verify that the distance controller generates the correct linear velocity.

| ID        | Distance Condition         | Expected Result             |
| --------- | -------------------------- | --------------------------- |
| TC-DC-001 | Target too far             | Positive linear velocity    |
| TC-DC-002 | Target at desired distance | Linear velocity ≈ 0        |
| TC-DC-003 | Target slightly too close  | Stop or reduce velocity     |
| TC-DC-004 | Target extremely close     | Robot must not move forward |
| TC-DC-005 | Invalid distance           | Safe stop                   |

---

# 7. Differential Drive Tests

### Objective

Verify conversion from robot velocity to individual wheel velocities.

For wheel separation \(W\):

$$
V_L = V-\frac{\omega W}{2}
$$

$$
V_R = V+\frac{\omega W}{2}
$$

| ID        |   Linear Velocity | Angular Velocity | Expected                          |
| --------- | ----------------: | ---------------: | --------------------------------- |
| TC-DD-001 |                +V |                0 | Both wheels forward equally       |
| TC-DD-002 |                -V |                0 | Both wheels backward equally      |
| TC-DD-003 |                +V |              +ω | Right wheel faster                |
| TC-DD-004 |                +V |              -ω | Left wheel faster                 |
| TC-DD-005 |                 0 |              +ω | Wheels rotate opposite directions |
| TC-DD-006 | Excessive command |              Any | Wheel speeds saturated            |

---

# 8. Gesture Recognition Tests

## 8.1 Valid Password

Password gesture:

**🖐🏻 Open Palm**

Conditions:

* One hand.
* Palm facing camera.
* Five fingers extended.
* Hand sufficiently visible.
* Gesture confidence above threshold.
* Gesture confirmed across multiple frames.

| ID        | Condition                                | Expected Result          |
| --------- | ---------------------------------------- | ------------------------ |
| TC-GR-001 | Clear open palm                          | Recognized               |
| TC-GR-002 | Open palm for only one frame             | Not immediately accepted |
| TC-GR-003 | Open palm maintained for required frames | Accepted                 |
| TC-GR-004 | Closed fist                              | Rejected                 |
| TC-GR-005 | Pointing gesture                         | Rejected                 |
| TC-GR-006 | Two fingers                              | Rejected                 |
| TC-GR-007 | Poor-confidence gesture                  | Rejected                 |
| TC-GR-008 | Hand outside usable frame                | Rejected                 |

---

# 9. Gesture-Person Association Tests

### Objective

Verify that the recognized gesture is associated with the correct tracked person.

| ID         | Scenario                                | Expected Result                  |
| ---------- | --------------------------------------- | -------------------------------- |
| TC-GPA-001 | One person + one gesture                | Gesture assigned to person       |
| TC-GPA-002 | Multiple people + gesture from person A | Assigned to A                    |
| TC-GPA-003 | Multiple people + gesture from person B | Assigned to B                    |
| TC-GPA-004 | Gesture not spatially associated        | Authentication rejected          |
| TC-GPA-005 | Person disappears during gesture        | Gesture not used for target lock |

---

# 10. Target Manager Tests

| ID        | Scenario                         | Expected Result            |
| --------- | -------------------------------- | -------------------------- |
| TC-TM-001 | Valid person authenticated       | Target ID stored           |
| TC-TM-002 | Target visible                   | Target updated             |
| TC-TM-003 | Target temporarily lost          | Loss timer starts          |
| TC-TM-004 | Target returns before timeout    | Target retained            |
| TC-TM-005 | Target lost beyond timeout       | Target cleared             |
| TC-TM-006 | New person appears after timeout | Not automatically selected |
| TC-TM-007 | `clear_target()` called        | Target ID becomes NONE     |

---

# 11. State Machine Tests

| ID        | Initial State | Event                      | Expected State      |
| --------- | ------------- | -------------------------- | ------------------- |
| TC-SM-001 | OFF           | Person nearby              | GREETING            |
| TC-SM-002 | GREETING      | Greeting complete          | OFF                 |
| TC-SM-003 | OFF           | Valid password             | TARGET_LOCK         |
| TC-SM-004 | TARGET_LOCK   | Target confirmed           | FOLLOW              |
| TC-SM-005 | FOLLOW        | Target visible             | FOLLOW              |
| TC-SM-006 | FOLLOW        | Target temporarily lost    | FOLLOW + loss timer |
| TC-SM-007 | FOLLOW        | Target returns             | FOLLOW              |
| TC-SM-008 | FOLLOW        | Target timeout             | OFF                 |
| TC-SM-009 | FOLLOW        | Valid password from target | DEACTIVATING        |
| TC-SM-010 | FOLLOW        | Password from other person | FOLLOW              |
| TC-SM-011 | DEACTIVATING  | Complete                   | OFF                 |
| TC-SM-012 | Any           | Critical error             | ERROR               |

---

# 12. UART Communication Tests

## 12.1 Raspberry Pi → ESP32

| ID          | Test                       | Expected Result              |
| ----------- | -------------------------- | ---------------------------- |
| TC-UART-001 | Send velocity command      | ESP32 receives valid command |
| TC-UART-002 | Send STOP                  | ESP32 stops motors           |
| TC-UART-003 | Send PING                  | ESP32 responds               |
| TC-UART-004 | Invalid packet             | Packet rejected              |
| TC-UART-005 | Corrupted packet           | Packet rejected safely       |
| TC-UART-006 | Communication interruption | ESP32 watchdog stops motors  |

---

# 13. ESP32 Motor Control Tests

| ID        | Scenario                 | Expected Result                         |
| --------- | ------------------------ | --------------------------------------- |
| TC-MC-001 | Left wheel command       | Left motor responds                     |
| TC-MC-002 | Right wheel command      | Right motor responds                    |
| TC-MC-003 | Equal wheel commands     | Straight movement                       |
| TC-MC-004 | Different wheel commands | Differential turning                    |
| TC-MC-005 | STOP command             | Both motors stop                        |
| TC-MC-006 | UART timeout             | Both motors stop                        |
| TC-MC-007 | Encoder feedback         | Correct speed measurement               |
| TC-MC-008 | PID enabled              | Actual speed approaches commanded speed |

---

# 14. HMI Tests

| ID         | Robot State  | Expected HMI         |
| ---------- | ------------ | -------------------- |
| TC-HMI-001 | OFF          | Live camera          |
| TC-HMI-002 | GREETING     | Greeting animation   |
| TC-HMI-003 | TARGET_LOCK  | Activation animation |
| TC-HMI-004 | FOLLOW       | Robot face           |
| TC-HMI-005 | Target lost  | Lost/warning face    |
| TC-HMI-006 | DEACTIVATING | Goodbye animation    |
| TC-HMI-007 | ERROR        | Error screen         |

---

# 15. Speech Tests

| ID        | Event                        | Expected Speech           |
| --------- | ---------------------------- | ------------------------- |
| TC-SP-001 | Person enters greeting range | Welcome speech            |
| TC-SP-002 | Password accepted            | Activation speech         |
| TC-SP-003 | Target locked                | Follow speech             |
| TC-SP-004 | Normal following             | Occasional follow speech  |
| TC-SP-005 | Target temporarily lost      | “Where are you?”        |
| TC-SP-006 | Target timeout               | “I can’t find you.”    |
| TC-SP-007 | Target deactivates           | “Okay! See you later!”  |
| TC-SP-008 | Error                        | “Something went wrong.” |

Speech must not block motor control.

---

# 16. Integration Tests

## 16.1 Authentication Flow

```text
Person enters range
        ↓
Person detected
        ↓
Greeting
        ↓
Open palm
        ↓
Gesture recognized
        ↓
Gesture associated with person
        ↓
Authentication successful
        ↓
Target locked
        ↓
FOLLOW
```

Expected result:

The person performing the valid password gesture becomes the target.

---

## 16.2 Follow Flow

```text
Target Detection
      ↓
Target Tracking
      ↓
Target Center
      +
Distance
      ↓
Follow Controller
      ↓
Differential Drive
      ↓
Wheel Commands
      ↓
ESP32
      ↓
PID
      ↓
Motors
```

Expected result:

NEXUS follows the locked target while maintaining safe distance and horizontal alignment.

---

# 17. Target-Loss Tests

Target-loss behavior is safety-critical.

### Test procedure

1. Activate NEXUS.
2. Confirm target is locked.
3. Allow NEXUS to follow normally.
4. Move target outside camera visibility.
5. Measure loss duration.
6. Observe robot behavior.

### Expected behavior

```text
Target visible
      ↓
Target disappears
      ↓
Loss timer starts
      ↓
Target returns before timeout
      ↓
FOLLOW continues
```

If the target remains lost:

```text
Target lost
      ↓
Timeout exceeded
      ↓
STOP
      ↓
Clear target
      ↓
OFF
      ↓
Live camera
      ↓
New password required
```

---

# 18. Multi-Person Tests

These tests verify that NEXUS does not accidentally switch targets.

### Scenario A

Person A authenticates.

Person B walks into the scene.

Expected:

* NEXUS continues following Person A.
* Person B does not become the target.

### Scenario B

Person B performs the password gesture.

Expected:

* Gesture from Person B is ignored.
* Person A remains the target.

### Scenario C

Person A performs the password gesture.

Expected:

* NEXUS deactivates.

---

# 19. Safety Tests

Safety tests have priority P0.

| ID          | Failure Condition                               | Expected Safety Response    |
| ----------- | ----------------------------------------------- | --------------------------- |
| TC-SAFE-001 | Target timeout                                  | Motors stop                 |
| TC-SAFE-002 | UART disconnected                               | ESP32 stops motors          |
| TC-SAFE-003 | Invalid velocity command                        | Command rejected            |
| TC-SAFE-004 | Distance sensor invalid                         | Safe movement behavior      |
| TC-SAFE-005 | Target data invalid                             | No normal follow command    |
| TC-SAFE-006 | Raspberry Pi application stops sending commands | ESP32 watchdog stops motors |
| TC-SAFE-007 | Emergency STOP command                          | Immediate motor stop        |
| TC-SAFE-008 | Excessive wheel velocity                        | Command saturated           |

---

# 20. Performance Tests

The system should initially target approximately:

| Component           |         Target Rate |
| ------------------- | ------------------: |
| Camera              |              30 FPS |
| Person Detection    |          10–20 FPS |
| Person Tracking     |          20–30 FPS |
| Gesture Recognition |          10–20 FPS |
| Distance Sensor     |           10–20 Hz |
| Follow Controller   |           20–50 Hz |
| UART Command        |              ~30 Hz |
| ESP32 PID           | High-frequency loop |

Performance testing should measure:

* Processing latency.
* Frame rate.
* CPU utilization.
* Memory utilization.
* UART latency.
* Control-loop timing.
* Detection/tracking stability.

---

# 21. End-to-End Test

The final system test shall execute the following scenario:

1. Power on NEXUS.
2. NEXUS enters `OFF`.
3. Live camera is displayed.
4. Person approaches NEXUS.
5. NEXUS detects the person.
6. NEXUS plays the welcome speech.
7. Person shows 🖐🏻 open palm.
8. NEXUS recognizes the gesture.
9. NEXUS associates the gesture with the correct person.
10. NEXUS locks the person's Track ID.
11. NEXUS enters `FOLLOW`.
12. NEXUS follows the target.
13. Target moves left and right.
14. NEXUS corrects its orientation.
15. Target changes distance.
16. NEXUS adjusts forward velocity.
17. Another person enters the scene.
18. NEXUS continues following the original target.
19. Original target shows 🖐🏻 open palm.
20. NEXUS deactivates.
21. Motors stop.
22. NEXUS returns to `OFF`.
23. Live camera is displayed.
24. A new password is required for another activation.

---

# 22. Test Result Classification

Each test shall be classified as:

* `PASS` — expected behavior achieved.
* `FAIL` — expected behavior not achieved.
* `BLOCKED` — test cannot be executed because of another unresolved issue.
* `NOT TESTED` — test has not yet been executed.

A failed P0 test blocks autonomous operation until the issue is resolved.

---

# 23. Test Evidence

Where practical, each test should produce evidence such as:

* Console logs.
* Recorded video.
* Screenshots.
* UART logs.
* Encoder measurements.
* Motor-speed measurements.
* Distance measurements.
* Detection/tracking results.
* HMI screenshots.
* Test-condition notes.

---

# 24. Exit Criteria

The NEXUS system may proceed to acceptance testing when:

* All P0 tests pass.
* All critical communication interfaces pass.
* Target-loss safety behavior passes.
* ESP32 watchdog behavior passes.
* Authentication flow passes.
* Target locking passes.
* Multi-person target protection passes.
* Basic following behavior passes.
* No unresolved safety-critical defects remain.

Acceptance testing is defined separately in `acceptance_criteria.md`.
