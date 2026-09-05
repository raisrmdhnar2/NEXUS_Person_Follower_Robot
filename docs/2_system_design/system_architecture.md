# NEXUS System Architecture

## 1. Purpose

This document defines the system-level architecture of **NEXUS**, a mobile human-following robot designed for the Technology and Information Department of Brawijaya University.

The purpose of this document is to translate the high-level NEXUS concept and top-level requirements into a concrete system architecture that can later be implemented as software and hardware modules.

This document defines:

* Overall system architecture
* Hardware/software partitioning
* Raspberry Pi and ESP32 responsibilities
* Major subsystems
* Data and control flow
* Perception pipeline
* Target authentication and tracking architecture
* Follow-control architecture
* Human-machine interface architecture
* Safety mechanisms

This document does **not** define detailed Python classes, function signatures, UART packet formats, or electrical pin assignments. Those are defined in lower-level design documents.

---

# 2. System Overview

NEXUS is a three-wheel differential-drive mobile robot consisting of:

* Raspberry Pi 5 as the high-level computing platform
* ESP32 as the low-level motor-control platform
* Camera for visual perception
* Distance sensor for proximity and follow-distance measurement
* Two rear motorized wheels
* One front passive caster wheel
* Motor encoders
* Motor driver
* Display/monitor
* Speaker/audio output

The system is divided into two major computational layers:

```text
┌───────────────────────────────────────────────┐
│                  NEXUS ROBOT                  │
│                                               │
│  ┌─────────────────────┐                      │
│  │   Raspberry Pi 5    │                      │
│  │   High-Level Layer  │                      │
│  │                     │                      │
│  │  Camera             │                      │
│  │  Person Detection   │                      │
│  │  Person Tracking    │                      │
│  │  Gesture Recognition│                      │
│  │  Authentication     │                      │
│  │  Target Management  │                      │
│  │  State Machine      │                      │
│  │  Follow Controller  │                      │
│  │  HMI / Speech       │                      │
│  └──────────┬──────────┘                      │
│             │ UART                             │
│             ▼                                  │
│  ┌─────────────────────┐                      │
│  │       ESP32         │                      │
│  │   Low-Level Layer   │                      │
│  │                     │                      │
│  │  UART Parser        │                      │
│  │  Encoder Reading    │                      │
│  │  PID Controllers    │                      │
│  │  PWM Generation     │                      │
│  │  Motor Control      │                      │
│  └──────────┬──────────┘                      │
│             │                                  │
│       ┌─────┴─────┐                            │
│       ▼           ▼                            │
│  Rear-Left    Rear-Right                      │
│    Motor         Motor                         │
│                                               │
│  Front Passive Caster Wheel                   │
└───────────────────────────────────────────────┘
```

---

# 3. Design Principles

NEXUS follows several architectural principles.

## 3.1 High-Level and Low-Level Separation

The Raspberry Pi handles computationally intensive and decision-making tasks.

The ESP32 handles deterministic real-time motor control.

```text
Raspberry Pi
    ↓
"What should the robot do?"

ESP32
    ↓
"How should the motors physically achieve it?"
```

The ESP32 must not make high-level decisions about:

* Who the target is
* Whether a password is valid
* Whether the robot should activate
* Whether the robot should deactivate
* Which person to follow
* Speech
* HMI state

---

## 3.2 Safety-Critical Motor Control

Motor control must remain independent from speech, HMI rendering, and other non-critical processes.

If communication from the Raspberry Pi is lost, the ESP32 must automatically stop the motors after a configurable communication timeout.

```text
UART communication lost
        ↓
ESP32 timeout
        ↓
Motor command = STOP
        ↓
Both motors stopped
```

---

## 3.3 Target-Locked Following

NEXUS does not simply follow the nearest person.

After authentication, the robot associates the valid password gesture with a tracked person and stores that person's tracking ID as the target.

```text
Valid Gesture
     ↓
Gesture-Person Association
     ↓
Tracked Person ID
     ↓
Target Lock
     ↓
Follow Only This ID
```

---

# 4. Hardware Architecture

## 4.1 Main Hardware Components

| Component       | Function                  | Processing Layer |
| --------------- | ------------------------- | ---------------- |
| Raspberry Pi 5  | High-level computation    | High-level       |
| Camera          | Visual perception         | Raspberry Pi     |
| Distance Sensor | Person proximity/distance | Raspberry Pi     |
| Monitor         | HMI                       | Raspberry Pi     |
| Speaker         | Speech output             | Raspberry Pi     |
| ESP32           | Real-time motor control   | Low-level        |
| Left Encoder    | Left wheel feedback       | ESP32            |
| Right Encoder   | Right wheel feedback      | ESP32            |
| Left Motor      | Rear-left propulsion      | ESP32            |
| Right Motor     | Rear-right propulsion     | ESP32            |
| Motor Driver    | Motor power switching     | ESP32            |
| Front Caster    | Passive support           | Mechanical       |

---

# 5. Mechanical Configuration

NEXUS uses a **three-wheel configuration**.

```text
                  FRONT
                    ↑

              ┌─────────────┐
              │             │
              │   CASTER    │
              │      ○      │
              │             │
              │    BODY     │
              │             │
              │             │
              │             │
              │             │
              │             │
              │             │
              │  ◉       ◉  │
              └─────────────┘
                 L       R

              REAR DRIVE WHEELS
```

The front wheel is a passive caster.

The rear-left and rear-right wheels are independently driven by DC geared motors.

This creates a differential-drive system.

---

# 6. Differential Drive

Let:

* \(V\) = desired linear velocity
* \(\omega\) = desired angular velocity
* \(W\) = distance between the two rear drive wheels

The desired wheel velocities are:

$$
V_L = V - \frac{\omega W}{2}
$$

$$
V_R = V + \frac{\omega W}{2}
$$

where:

* \(V_L\) = left wheel velocity
* \(V_R\) = right wheel velocity

The front caster does not participate in velocity control.

---

# 7. Software Architecture

The Raspberry Pi software is divided into several subsystems.

```text
Raspberry Pi
│
├── Perception
│   ├── Camera
│   ├── Person Detection
│   ├── Person Tracking
│   └── Gesture Recognition
│
├── Target Management
│   ├── Proximity Detection
│   ├── Gesture-Person Association
│   ├── Authentication
│   └── Target Lock
│
├── Robot State
│   └── State Machine
│
├── Follow Control
│   ├── Center Controller
│   ├── Distance Controller
│   ├── Follow Controller
│   └── Differential Drive
│
├── Communication
│   └── Raspberry Pi ↔ ESP32 UART
│
└── HMI
    ├── Live Camera
    ├── Robot Face
    └── Speech
```

---

# 8. Perception Subsystem

The perception subsystem processes camera data and produces information about people and gestures.

## 8.1 Camera

The camera continuously captures frames.

During the `OFF` state, the camera remains active because it is required for:

* Person detection
* Proximity/greeting detection
* Password detection

The live camera feed is also displayed on the monitor while the robot is `OFF`.

---

## 8.2 Person Detection

The person detector identifies people in each camera frame.

Output:

```text
PersonDetection
├── bounding box
├── confidence
└── class
```

A lightweight object detector such as YOLO is expected to be used.

---

## 8.3 Person Tracking

The tracker assigns persistent IDs to detected people.

Example:

```text
Person #1
Person #2
Person #3
```

Each tracked person contains information such as:

```text
Track ID
Bounding Box
Confidence
Position
Tracking Status
```

A tracking algorithm such as ByteTrack or BoT-SORT may be used.

---

## 8.4 Gesture Recognition

The gesture recognition subsystem detects the predefined password gesture.

The gesture itself is not sufficient for authentication.

The system must determine **which tracked person performed the gesture**.

```text
Camera Frame
     │
     ├── Person Detection
     │       ↓
     │   Person Tracks
     │
     └── Gesture Detection
             ↓
        Gesture Position
             │
             ▼
     Gesture-Person Association
             │
             ▼
        Person Track ID
```

---

# 9. Authentication Architecture

NEXUS uses a predefined hand gesture as its password.

Authentication consists of:

```text
Gesture detected
       ↓
Is gesture valid?
       ↓
YES
       ↓
Identify person associated with gesture
       ↓
Check robot state
       ↓
Perform appropriate action
```

The same password gesture has different consequences depending on the robot state.

### When OFF

```text
Valid gesture
     ↓
Identify person
     ↓
Lock person's Track ID
     ↓
Activate robot
```

### When ACTIVE

```text
Valid gesture
     ↓
Identify person
     ↓
Is this the locked target?
     │
     ├── YES → Deactivate
     │
     └── NO  → Ignore
```

Therefore, another person cannot deactivate the robot simply by showing the correct gesture.

---

# 10. Target Management

The Target Manager is responsible for maintaining the currently selected person.

A target can be represented conceptually as:

```text
Target
├── track_id
├── bounding_box
├── center_position
├── distance
└── tracking_status
```

When authentication succeeds:

```text
Authenticated Track ID
        ↓
Target Manager
        ↓
target_id = authenticated_track_id
```

During following:

```text
Current Tracks
      ↓
Find target_id
      ↓
Target Position
      ↓
Follow Controller
```

---

# 11. Target Center Tracking

The target's horizontal position is used to control robot orientation.

For an image width \(W\):

$$
x_{camera} = \frac{W}{2}
$$

For the target bounding box:

$$
x_c = \frac{x_1+x_2}{2}
$$

Horizontal error:

$$
e_x=x_c-x_{camera}
$$

Interpretation:

```text
e_x < 0  → Target is left
e_x ≈ 0  → Target is centered
e_x > 0  → Target is right
```

The center controller uses this error to generate angular velocity.

---

# 12. Distance Control

A distance sensor provides the estimated distance between NEXUS and the target.

Let:

$$
D_{person}
$$

be the measured target distance and:

$$
D_{target}
$$

be the desired following distance.

Distance error:

$$
e_d=D_{person}-D_{target}
$$

Interpretation:

```text
e_d > 0  → Target is too far
e_d ≈ 0  → Target is at desired distance
e_d < 0  → Target is too close
```

Initial behavior:

```text
Too far
   ↓
Move forward

Desired distance
   ↓
Stop / move slowly

Too close
   ↓
Stop
```

Automatic reverse movement should initially be avoided until the safety and control behavior has been validated.

---

# 13. Follow Controller

The Follow Controller combines:

* Target horizontal position
* Target distance

to generate:

```text
Linear velocity V
Angular velocity ω
```

Conceptually:

```text
Target Tracking
      │
      ├── Horizontal Error ──► Center Controller
      │                              │
      │                              ▼
      │                              ω
      │
      └── Distance Error ─────► Distance Controller
                                     │
                                     ▼
                                     V
                                     │
                                     ▼
                              Follow Controller
                                     │
                                     ▼
                                  V, ω
```

---

# 14. Differential Drive Controller

The differential-drive controller converts:

$$
V,\omega
$$

into:

$$
V_L,V_R
$$

using:

$$
V_L=V-\frac{\omega W}{2}
$$

$$
V_R=V+\frac{\omega W}{2}
$$

The resulting commands are transmitted to the ESP32.

```text
V, ω
 │
 ▼
Differential Drive
 │
 ├── V_L
 └── V_R
      │
      ▼
     UART
```

---

# 15. ESP32 Motor-Control Architecture

The ESP32 receives wheel commands from the Raspberry Pi.

```text
UART
 │
 ▼
Command Parser
 │
 ├── Left Wheel Command
 └── Right Wheel Command
        │
        ▼
   PID Controllers
        │
        ├──────────────┐
        ▼              ▼
   Left PWM        Right PWM
        │              │
        ▼              ▼
   Left Motor      Right Motor
        │              │
        ▼              ▼
   Left Encoder    Right Encoder
        │              │
        └──────┬───────┘
               ▼
          PID Feedback
```

The encoder provides feedback for closed-loop wheel-speed control.

---

# 16. Raspberry Pi ↔ ESP32 Responsibility Boundary

## Raspberry Pi

Responsible for:

* Camera
* Person detection
* Person tracking
* Gesture recognition
* Gesture-person association
* Authentication
* Target selection
* Target locking
* State machine
* Follow control
* Differential-drive calculation
* HMI
* Speech
* High-level safety decisions
* UART command generation

## ESP32

Responsible for:

* UART communication
* Command parsing
* Encoder reading
* Wheel-speed measurement
* PID control
* PWM generation
* Motor control
* Communication timeout
* Immediate motor stop

---

# 17. HMI Architecture

The monitor provides two primary visual modes.

## OFF

Display:

```text
Live Camera
```

The camera remains visible while NEXUS waits for a nearby person and password.

## ACTIVE

Display:

```text
Robot Face
```

Example expressions:

```text
Normal     (•‿•)
Happy      (^‿^)
Lost       (•︵•)
Confused   (⊙_⊙)
Error      (×_×)
```

---

# 18. Speech Architecture

Speech is controlled by a dedicated Speech Manager.

Speech events include:

| Event                                 | Speech                                                                                                                                                  |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Person detected within greeting range | "Welcome to the Technology and Information Department of Brawijaya University! Hello! I’m NEXUS. I’m ready to follow you. Please show me the password." |
| Password accepted / Activation        | "Hello! Nice to see you."                                                                                                                               |
| Target locked                         | "I’ll follow you."                                                                                                                                      |
| Following normally                    | "I’m right behind you."                                                                                                                                 |
| Target temporarily lost               | "Where are you?"                                                                                                                                        |
| Target lost → timeout                 | "I can’t find you."                                                                                                                                     |
| Deactivation by target                | "Okay! See you later!"                                                                                                                                  |
| System error                          | "Something went wrong."                                                                                                                                 |

Speech must not block safety-critical operations.

For example:

```text
Target Lost
     ↓
Motor Stop
     ↓
Start Loss Timer
     ↓
Speech
```

not:

```text
Target Lost
     ↓
Speech
     ↓
Motor Stop
```

---

# 19. Proximity and Greeting Architecture

While `OFF`, NEXUS continuously monitors for nearby people.

The primary proximity measurement should use the distance sensor when reliable.

Camera-based information, such as bounding-box size, can supplement the distance measurement.

```text
Person Detection
       +
Distance Sensor
       ↓
Proximity Manager
       ↓
Person within greeting range?
       │
       ├── NO → Continue monitoring
       │
       └── YES
             ↓
          GREETING
```

Greeting must not repeatedly trigger while the same person remains within range.

A greeting interaction flag/cooldown should be used.

The greeting permission is reset when the person leaves the configured greeting range.

---

# 20. Target-Lost Safety Architecture

During `FOLLOW`, if the locked target cannot be detected/tracked:

```text
Target Lost
     ↓
Start Loss Timer
     ↓
Continue monitoring
     │
     ├── Target returns before timeout
     │       ↓
     │    Continue FOLLOW
     │
     └── Timeout exceeded
             ↓
        Stop Motors
             ↓
        Clear Target
             ↓
             OFF
```

After the timeout is exceeded, NEXUS must **not automatically search for or reacquire another person**.

The robot must return to `OFF` and require a new valid password.

---

# 21. Complete System Data Flow

The complete high-level flow is:

```text
                         CAMERA
                           │
                           ▼
                  PERSON DETECTION
                           │
                           ▼
                   PERSON TRACKING
                           │
             ┌─────────────┴─────────────┐
             │                           │
             ▼                           ▼
       PERSON TRACKS              GESTURE RECOGNITION
             │                           │
             │                           ▼
             │                  GESTURE-PERSON
             │                   ASSOCIATION
             │                           │
             └─────────────┬─────────────┘
                           ▼
                     AUTHENTICATION
                           │
                           ▼
                    TARGET MANAGER
                           │
                           ▼
                    STATE MACHINE
                           │
             ┌─────────────┴─────────────┐
             │                           │
             ▼                           ▼
          GREETING                     FOLLOW
             │                           │
             ▼                           ▼
          SPEECH                TARGET POSITION
                                         │
                              ┌──────────┴──────────┐
                              ▼                     ▼
                       CENTER CONTROL       DISTANCE CONTROL
                              │                     │
                              ▼                     ▼
                              ω                     V
                               \                   /
                                \                 /
                                 ▼               ▼
                              FOLLOW CONTROLLER
                                      │
                                      ▼
                               DIFFERENTIAL DRIVE
                                      │
                                 ┌────┴────┐
                                 ▼         ▼
                                V_L       V_R
                                 │         │
                                 └────┬────┘
                                      ▼
                                    UART
                                      │
                                      ▼
                                    ESP32
                                      │
                              ┌───────┴────────┐
                              ▼                ▼
                         LEFT PID          RIGHT PID
                              │                │
                              ▼                ▼
                         LEFT MOTOR       RIGHT MOTOR
                              │                │
                              └───────┬────────┘
                                      ▼
                                   ROBOT
```

---

# 22. Safety and Failure Handling

NEXUS shall prioritize safe motor behavior over non-critical functions.

Important safety conditions include:

### Target loss

```text
Target lost
→ loss timer
→ timeout
→ motor stop
→ target cleared
→ OFF
```

### UART failure

```text
UART timeout
→ ESP32 detects communication loss
→ stop motors
```

### Invalid password

```text
Invalid gesture
→ authentication rejected
→ robot remains in current state
```

### Wrong person attempts deactivation

```text
Gesture valid
+
Person != target_id
→ ignore deactivation
```

### System error

```text
Critical error
→ stop motors
→ ERROR or OFF
→ display error state
→ speech error notification
```

---

# 23. Expected Control Frequencies

The system should not execute every subsystem at the same frequency.

Initial target frequencies:

| Subsystem           |                   Target Rate |
| ------------------- | ----------------------------: |
| Camera              |                       ~30 FPS |
| Person Detection    |                    ~10–20 FPS |
| Person Tracking     |                    ~20–30 FPS |
| Gesture Recognition |                    ~10–20 FPS |
| Distance Sensor     |                     ~10–20 Hz |
| Follow Controller   |                     ~20–50 Hz |
| UART Commands       |                     ~20–50 Hz |
| ESP32 PID           | High-frequency real-time loop |

These values are initial engineering targets and should be calibrated experimentally.

---

# 24. System-Level Architecture Summary

NEXUS follows the architecture:

```text
PERCEPTION
    ↓
AUTHENTICATION
    ↓
TARGET LOCK
    ↓
TARGET TRACKING
    ↓
SENSOR PROCESSING
    ↓
FOLLOW CONTROL
    ↓
DIFFERENTIAL DRIVE
    ↓
UART
    ↓
ESP32
    ↓
PID
    ↓
MOTORS
```

In parallel:

```text
ROBOT STATE
    ↓
HMI
    ├── Live Camera
    └── Robot Face

ROBOT EVENTS
    ↓
SPEECH MANAGER
```

The architecture separates **perception and decision-making** from **real-time motor control**, allowing NEXUS to be developed, tested, and debugged subsystem by subsystem.
