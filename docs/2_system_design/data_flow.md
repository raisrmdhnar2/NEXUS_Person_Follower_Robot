
# NEXUS Data Flow

## 1. Purpose

This document defines how information moves between NEXUS subsystems.

The purpose is to establish a clear data pipeline from physical sensors and camera input to high-level decisions and finally to motor actuation.

The main NEXUS data pipeline is:

```text
Perception
    ↓
Authentication / Target Management
    ↓
Robot State
    ↓
Follow Control
    ↓
Differential Drive
    ↓
Communication
    ↓
ESP32 Motor Control
```

---

# 2. High-Level Data Flow

```text
                         ┌──────────────┐
                         │    CAMERA    │
                         └──────┬───────┘
                                │
                         Image Frame
                                │
                ┌───────────────┴───────────────┐
                │                               │
                ▼                               ▼
       Person Detection                  Gesture Recognition
                │                               │
       Person Detections                  Gestures
                │                               │
                ▼                               ▼
       Person Tracking              Gesture-Person Association
                │                               │
          Tracked Persons                        │
                │                               │
                └───────────────┬───────────────┘
                                ▼
                         AUTHENTICATION
                                │
                                ▼
                         TARGET MANAGER
                                │
                                ▼
                          STATE MACHINE
                                │
                         ┌──────┴──────┐
                         │             │
                         ▼             ▼
                      GREETING       FOLLOW
                         │             │
                         ▼             ▼
                      SPEECH     FOLLOW CONTROLLER
                                       │
                                  ┌────┴────┐
                                  ▼         ▼
                              Linear V   Angular ω
                                  │         │
                                  └────┬────┘
                                       ▼
                              DIFFERENTIAL DRIVE
                                       │
                                ┌──────┴──────┐
                                ▼             ▼
                              V_left        V_right
                                │             │
                                └──────┬──────┘
                                       ▼
                                      UART
                                       │
                                       ▼
                                     ESP32
                                       │
                                ┌──────┴──────┐
                                ▼             ▼
                              LEFT          RIGHT
                               PID            PID
                                │             │
                                ▼             ▼
                              MOTOR         MOTOR
                                │             │
                                ▼             ▼
                             ENCODER       ENCODER
                                │             │
                                └──────┬──────┘
                                       ▼
                                    Feedback
```

---

# 3. Data Categories

NEXUS exchanges several major types of data.

| Data                  | Source              | Destination             |
| --------------------- | ------------------- | ----------------------- |
| Image Frame           | Camera              | Vision modules          |
| Person Detection      | Detector            | Tracker                 |
| Tracked Person        | Tracker             | Target Manager          |
| Gesture Detection     | Gesture Recognition | Association             |
| Gesture-Person ID     | Association         | Authentication          |
| Authentication Result | Authentication      | State / Target Manager  |
| Target State          | Target Manager      | Follow Controller       |
| Distance              | Distance Sensor     | Target / Follow Control |
| Robot State           | State Machine       | HMI / Speech / Control  |
| \(V,\omega\)          | Follow Controller   | Differential Drive      |
| \(V_L,V_R\)           | Differential Drive  | UART                    |
| Wheel Command         | UART                | ESP32                   |
| Encoder Feedback      | ESP32               | UART / Raspberry Pi     |
| Motor Status          | ESP32               | Raspberry Pi            |

---

# 4. Camera Data Flow

The camera is the primary visual data source.

```text
Camera
  │
  ▼
Image Frame
  │
  ├──────────────► Person Detection
  │
  ├──────────────► Gesture Recognition
  │
  └──────────────► Live Camera HMI
```

The same camera frame may be consumed by multiple modules.

The Camera subsystem should provide a consistent frame stream without allowing downstream modules to directly control the camera.

---

# 5. Person Detection Data Flow

```text
Image Frame
     │
     ▼
Person Detector
     │
     ▼
PersonDetection[]
```

Each detection contains conceptually:

```text
PersonDetection
├── bounding_box
├── confidence
└── class
```

Example:

```text
PersonDetection:
    bbox = [100, 120, 350, 600]
    confidence = 0.92
    class = PERSON
```

---

# 6. Person Tracking Data Flow

```text
PersonDetection[]
       │
       ▼
Person Tracker
       │
       ▼
TrackedPerson[]
```

The tracker adds persistent identity.

Example:

```text
TrackedPerson
├── track_id = 7
├── bbox
├── center
├── confidence
└── status
```

The tracking ID becomes important during authentication and following.

---

# 7. Gesture Data Flow

```text
Image Frame
     │
     ▼
Gesture Recognition
     │
     ▼
GestureDetection
```

Example:

```text
GestureDetection
├── gesture_type = PASSWORD
├── confidence = 0.94
├── hand_bbox
└── hand_center
```

At this stage, the system knows:

> "A valid-looking password gesture exists."

It does not yet know which person performed it.

---

# 8. Gesture-Person Association Flow

The gesture is associated with a tracked person.

```text
TrackedPerson[]
       +
GestureDetection
       │
       ▼
Gesture-Person Association
       │
       ▼
gesture_person_id
```

Example:

```text
Tracked Persons:

ID 2
ID 5
ID 7

Gesture:
    hand_center = [500, 280]

Association:
    gesture_person_id = 7
```

This association is essential for secure activation and deactivation.

---

# 9. Authentication Data Flow

```text
Gesture Detection
       │
       ▼
Gesture-Person Association
       │
       ▼
Authentication
       │
       ├── Valid
       └── Invalid
```

For a valid gesture:

```text
Authentication Result
├── valid = true
├── person_id = 7
└── event = PASSWORD_ACCEPTED
```

---

# 10. OFF Authentication Flow

When NEXUS is `OFF`:

```text
Valid Password
      │
      ▼
Authenticated Person ID
      │
      ▼
Target Manager
      │
      ▼
target_id = authenticated_person_id
      │
      ▼
TARGET_LOCK
      │
      ▼
FOLLOW
```

The authenticated person becomes the target.

---

# 11. FOLLOW Deactivation Data Flow

When NEXUS is `FOLLOW`:

```text
Valid Password
      │
      ▼
gesture_person_id
      │
      ▼
Compare with target_id
      │
      ├── Equal
      │     ↓
      │  DEACTIVATING
      │
      └── Not Equal
            ↓
          IGNORE
```

This comparison prevents other people from deactivating NEXUS.

---

# 12. Proximity Data Flow

The distance sensor provides physical distance information.

```text
Distance Sensor
      │
      ▼
Measured Distance
      │
      ▼
Proximity Manager
      │
      ├── Nearby
      └── Not Nearby
```

Combined with person detection:

```text
Person Track
      +
Distance
      │
      ▼
Proximity Manager
      │
      ▼
Person Nearby Event
```

---

# 13. Greeting Data Flow

The greeting pipeline is:

```text
Person Detection
      +
Distance Measurement
      │
      ▼
Proximity Manager
      │
      ▼
Person within greeting range
      │
      ▼
PERSON_NEARBY event
      │
      ▼
State Machine
      │
      ▼
GREETING
      │
      ├──────────► HMI
      │
      └──────────► Speech Manager
```

The greeting event does not create a target.

---

# 14. Target Data Flow

Once a target is locked:

```text
Person Tracker
      │
      ▼
TrackedPerson[]
      │
      ▼
Target Manager
      │
      ▼
Find target_id
      │
      ▼
Target State
```

The Target Manager produces the current target information.

Conceptually:

```text
Target
├── track_id
├── bbox
├── center_x
├── center_y
├── distance
├── visible
└── tracking_status
```

---

# 15. Target Position Data Flow

The target bounding box provides horizontal position.

For image width \(W\):

$$
x_{camera}=\frac{W}{2}
$$

Target center:

$$
x_c=\frac{x_1+x_2}{2}
$$

Horizontal error:

$$
e_x=x_c-x_{camera}
$$

Data flow:

```text
Target Bounding Box
       │
       ▼
Target Center
       │
       ▼
Horizontal Error
       │
       ▼
Center Controller
       │
       ▼
Angular Velocity ω
```

---

# 16. Target Distance Data Flow

Distance flow:

```text
Distance Sensor
       │
       ▼
Measured Distance
       │
       ▼
Target Distance
       │
       ▼
Distance Error
       │
       ▼
Distance Controller
       │
       ▼
Linear Velocity V
```

Distance error:

$$
e_d=D_{person}-D_{target}
$$

---

# 17. Follow Control Data Flow

The Follow Controller combines two control dimensions:

```text
Target Position
      │
      ▼
Center Controller
      │
      ▼
      ω
```

and:

```text
Target Distance
      │
      ▼
Distance Controller
      │
      ▼
      V
```

These are combined:

```text
V
+
ω
│
▼
Follow Controller
│
▼
Velocity Command
```

---

# 18. Differential Drive Data Flow

The robot-level velocity command is converted to wheel velocities.

Input:

```text
V
ω
```

Processing:

$$
V_L=V-\frac{\omega W}{2}
$$

$$
V_R=V+\frac{\omega W}{2}
$$

Output:

```text
V_left
V_right
```

Flow:

```text
V, ω
 │
 ▼
Differential Drive
 │
 ├────────────► V_left
 │
 └────────────► V_right
```

---

# 19. Raspberry Pi → ESP32 Data Flow

The Raspberry Pi generates wheel commands.

```text
Follow Controller
      │
      ▼
Differential Drive
      │
      ▼
V_left, V_right
      │
      ▼
Command Formatter
      │
      ▼
UART
      │
      ▼
ESP32
```

The communication layer is responsible for converting internal velocity commands into the defined UART protocol.

---

# 20. ESP32 Data Flow

The ESP32 receives wheel commands.

```text
UART
 │
 ▼
Command Parser
 │
 ▼
Left Wheel Command ──────► Left PID
                                │
                                ▼
                           Left PWM
                                │
                                ▼
                           Left Motor
                                │
                                ▼
                           Left Encoder
                                │
                                └──────► Feedback

Right Wheel Command ─────► Right PID
                                │
                                ▼
                           Right PWM
                                │
                                ▼
                           Right Motor
                                │
                                ▼
                           Right Encoder
                                │
                                └──────► Feedback
```

---

# 21. Encoder Feedback Flow

The encoder provides feedback to the motor controller.

```text
Motor Rotation
      │
      ▼
Encoder
      │
      ▼
Pulse Count
      │
      ▼
Wheel Speed
      │
      ▼
PID Feedback
```

The PID controller compares:

```text
Desired Wheel Speed
        +
Measured Wheel Speed
        ↓
PID
        ↓
PWM
```

---

# 22. ESP32 → Raspberry Pi Feedback

The ESP32 can provide status and feedback to the Raspberry Pi.

```text
Left Encoder
Right Encoder
Motor Status
Error Status
      │
      ▼
ESP32
      │
      ▼
UART
      │
      ▼
Raspberry Pi
      │
      ▼
Communication Manager
```

This information can be used for:

* Diagnostics
* Logging
* Control monitoring
* Debugging
* Future odometry

---

# 23. State Data Flow

The State Machine receives events from multiple subsystems.

```text
Person Detection
       │
       ▼
Proximity Manager
       │
       ▼
PERSON_NEARBY
       │
       ▼
State Machine
```

Authentication:

```text
Gesture
   +
Person Association
   ↓
Authentication
   ↓
PASSWORD_ACCEPTED
   ↓
State Machine
```

Target loss:

```text
Target Manager
      ↓
TARGET_LOST
      ↓
State Machine
```

Target timeout:

```text
Target Manager
      ↓
TARGET_LOST_TIMEOUT
      ↓
State Machine
```

Target deactivation:

```text
Authentication
      +
Target ID
      ↓
TARGET_DEACTIVATION
      ↓
State Machine
```

---

# 24. State → HMI Data Flow

The State Machine provides the current robot state to the HMI.

```text
State Machine
      │
      ▼
Robot State
      │
      ▼
HMI Manager
      │
 ┌────┼──────────────┐
 ▼    ▼              ▼
Live  Robot Face   Animation
Camera
```

Example:

```text
State = OFF
    ↓
Live Camera
```

```text
State = FOLLOW
    ↓
Robot Face
```

---

# 25. State → Speech Data Flow

The State Machine and event system generate speech events.

```text
Robot Event
     │
     ▼
Speech Manager
     │
     ▼
Audio Output
     │
     ▼
Speaker
```

Example:

```text
PERSON_NEARBY
     ↓
GREETING
     ↓
Speech Event
     ↓
Welcome message
```

---

# 26. Target-Lost Data Flow

Target loss has a dedicated safety flow.

```text
Target Manager
      │
      ▼
Target not detected
      │
      ▼
Start loss timer
      │
      ├──── Target returns ────► FOLLOW
      │
      └──── Timeout ───────────► TARGET_LOST_TIMEOUT
                                      │
                                      ▼
                                State Machine
                                      │
                                      ▼
                                     OFF
                                      │
                             ┌────────┴────────┐
                             ▼                 ▼
                        Motor STOP        Clear Target
```

The ESP32 also independently provides motor safety if the command stream stops.

---

# 27. Safety Data Flow

Safety has two layers.

## Layer 1 — Raspberry Pi

```text
Target Lost Timeout
      ↓
State Machine
      ↓
OFF
      ↓
STOP command
      ↓
ESP32
```

## Layer 2 — ESP32

```text
No valid UART command
      ↓
Communication Timeout
      ↓
Motor STOP
```

Therefore:

```text
                 Target Lost
                      │
                      ▼
              Raspberry Pi Logic
                      │
                      ▼
                  STOP Command
                      │
                      ▼
                    ESP32
                      │
                      ▼
                  Motor STOP


                 UART Failure
                      │
                      ▼
                    ESP32
                      │
                      ▼
              Communication Timeout
                      │
                      ▼
                  Motor STOP
```

---

# 28. Complete Operational Data Flow — Startup

When NEXUS is powered on:

```text
Power ON
   │
   ▼
Raspberry Pi Initialization
   │
   ├── Camera
   ├── Vision
   ├── Sensors
   ├── HMI
   ├── Speech
   └── UART
   │
   ▼
ESP32 Initialization
   │
   ├── UART
   ├── Encoders
   ├── PID
   └── Motors
   │
   ▼
System Ready
   │
   ▼
OFF
```

The robot does not greet immediately.

It waits until a person is detected within the configured greeting range.

---

# 29. Complete Operational Data Flow — Greeting

```text
Camera
  │
  ▼
Person Detection
  │
  ▼
Person Tracking
  │
  ▼
Distance Measurement
  │
  ▼
Proximity Manager
  │
  ▼
Person Nearby
  │
  ▼
State Machine
  │
  ▼
GREETING
  │
  ├────► HMI Greeting
  │
  └────► Speech
            │
            ▼
       Welcome Message
            │
            ▼
           OFF
```

---

# 30. Complete Operational Data Flow — Activation

```text
Camera
  │
  ├────────► Person Detection
  │                 │
  │                 ▼
  │            Person Tracking
  │                 │
  │                 │
  └────────► Gesture Recognition
                    │
                    ▼
            Gesture-Person Association
                    │
                    ▼
              Authentication
                    │
                    ▼
             Valid Password
                    │
                    ▼
             Authenticated ID
                    │
                    ▼
             Target Manager
                    │
                    ▼
             target_id = ID
                    │
                    ▼
              TARGET_LOCK
                    │
                    ▼
                  FOLLOW
```

---

# 31. Complete Operational Data Flow — Following

```text
Camera
  │
  ▼
Person Detection
  │
  ▼
Person Tracking
  │
  ▼
Target Manager
  │
  ├──────────────► Target Position
  │                      │
  │                      ▼
  │               Center Controller
  │                      │
  │                      ▼
  │                      ω
  │
  └──────────────► Target Distance
                         │
                         ▼
                  Distance Controller
                         │
                         ▼
                         V
                         │
                         └──────┐
                                ▼
                         Follow Controller
                                │
                                ▼
                              V, ω
                                │
                                ▼
                       Differential Drive
                                │
                         ┌──────┴──────┐
                         ▼             ▼
                       V_left        V_right
                         │             │
                         └──────┬──────┘
                                ▼
                               UART
                                │
                                ▼
                              ESP32
                         ┌──────┴──────┐
                         ▼             ▼
                       Left          Right
                        PID            PID
                         │             │
                         ▼             ▼
                       Motor         Motor
```

---

# 32. Complete Operational Data Flow — Deactivation

```text
FOLLOW
  │
  ▼
Camera
  │
  ▼
Gesture Recognition
  │
  ▼
Gesture-Person Association
  │
  ▼
Authentication
  │
  ▼
Valid Password
  │
  ▼
gesture_person_id
  │
  ▼
Compare with target_id
  │
  ├──── Different ────► Ignore
  │
  └──── Same ─────────► DEACTIVATING
                              │
                              ▼
                         Motor STOP
                              │
                         ┌────┴────┐
                         ▼         ▼
                      Speech      HMI
                         │         │
                         └────┬────┘
                              ▼
                             OFF
```

---

# 33. Complete Operational Data Flow — Target Loss

```text
FOLLOW
  │
  ▼
Person Tracking
  │
  ▼
Target Manager
  │
  ▼
Target unavailable
  │
  ▼
Loss Timer
  │
  ├──────────────► Target returns
  │                       │
  │                       ▼
  │                     FOLLOW
  │
  └──────────────► Timeout
                          │
                          ▼
                    Motor STOP
                          │
                          ▼
                    Clear Target
                          │
                          ▼
                         OFF
                          │
                          ▼
                    Live Camera
                          │
                          ▼
                  Wait for Password
```

---

# 34. Data Ownership

To avoid conflicting modifications, each important piece of data should have a primary owner.

| Data                       | Owner                  |
| -------------------------- | ---------------------- |
| Camera Frame               | Camera                 |
| Person Detections          | Person Detector        |
| Track IDs                  | Person Tracker         |
| Gesture Result             | Gesture Recognition    |
| Gesture-Person Association | Association Module     |
| Authentication Result      | Authentication         |
| `target_id`              | Target Manager         |
| Target Position            | Target Manager         |
| Target Distance            | Target/Sensor Manager  |
| Robot State                | State Machine          |
| Linear Velocity\(V\)       | Follow Controller      |
| Angular Velocity\(\omega\) | Follow Controller      |
| Left/Right Wheel Velocity  | Differential Drive     |
| UART Command               | Communication Manager  |
| Encoder Measurement        | ESP32 Encoder          |
| Motor PWM                  | ESP32 Motor Controller |

Other modules should consume this data rather than independently maintaining competing versions.

---

# 35. Data Flow Timing

Different data paths operate at different rates.

```text
Camera
~30 FPS
   │
   ├── Detection
   │   ~10–20 FPS
   │
   ├── Tracking
   │   ~20–30 FPS
   │
   └── Gesture
       ~10–20 FPS
```

Control:

```text
Distance Sensor
~10–20 Hz
      │
      ▼
Follow Controller
~20–50 Hz
      │
      ▼
UART
~20–50 Hz
      │
      ▼
ESP32 PID
High-frequency loop
```

The system should not force all processing into one synchronous loop.

---

# 36. Data Flow and State Interaction

The state machine determines which data is relevant.

## OFF

Relevant data:

```text
Camera
Person Detection
Tracking
Distance
Gesture
```

Purpose:

```text
Greeting detection
Authentication
```

## GREETING

Relevant data:

```text
Speech
HMI
```

## TARGET_LOCK

Relevant data:

```text
Authentication
Target ID
Tracking
```

## FOLLOW

Relevant data:

```text
Target position
Target distance
Gesture
Encoder/status feedback
```

## DEACTIVATING

Relevant data:

```text
Speech
HMI
Target clear
Motor stop
```

## ERROR

Relevant data:

```text
Error status
HMI
Speech
Motor stop
```

---

# 37. Critical Data Path

The most important real-time path is:

```text
Camera
  ↓
Person Detection
  ↓
Person Tracking
  ↓
Target Manager
  ↓
Target Position / Distance
  ↓
Follow Controller
  ↓
Differential Drive
  ↓
UART
  ↓
ESP32
  ↓
PID
  ↓
Motor
```

This path determines NEXUS's ability to follow the target smoothly.

Latency should therefore be minimized along this path.

---

# 38. Critical Safety Path

The most important safety path is:

```text
Target Lost
      ↓
Target Manager
      ↓
Loss Timer
      ↓
Timeout
      ↓
State Machine
      ↓
OFF
      ↓
STOP
      ↓
ESP32
      ↓
Motors STOP
```

Independent backup:

```text
UART Failure
      ↓
ESP32 Watchdog
      ↓
Motors STOP
```

---

# 39. Data Flow Design Rules

The following rules apply to the implementation.

### Rule 1

Raw camera frames should not be passed unnecessarily between unrelated modules.

### Rule 2

Vision modules should exchange structured data rather than modifying each other's internal state.

### Rule 3

`target_id` has one owner: Target Manager.

### Rule 4

Robot state has one owner: State Machine.

### Rule 5

Wheel velocity generation belongs to the Follow/Differential Drive layer.

### Rule 6

The Raspberry Pi sends desired wheel behavior; the ESP32 controls actual wheel behavior.

### Rule 7

Speech and HMI must not block the follow-control pipeline.

### Rule 8

Safety-critical motor stopping must not depend on speech or HMI.

### Rule 9

The ESP32 must stop motors when communication becomes invalid.

### Rule 10

After target-loss timeout, target identity must be cleared and NEXUS must return to `OFF`.

---

# 40. Final Data Flow Architecture

The NEXUS data architecture can be summarized as:

```text
                    PHYSICAL WORLD
                          │
                          ▼
                    ┌───────────┐
                    │  CAMERA   │
                    └─────┬─────┘
                          │
                          ▼
                    PERCEPTION
              ┌───────────┼───────────┐
              ▼           ▼           ▼
          Detection    Tracking    Gesture
              │           │           │
              └─────┬─────┴─────┬─────┘
                    │           │
                    ▼           ▼
                 TARGET      ASSOCIATION
                MANAGEMENT      │
                    │           ▼
                    │     AUTHENTICATION
                    │           │
                    └─────┬─────┘
                          ▼
                    STATE MACHINE
                          │
                ┌─────────┴─────────┐
                ▼                   ▼
             GREETING             FOLLOW
                │                   │
          ┌─────┴─────┐       ┌─────┴─────┐
          ▼           ▼       ▼           ▼
         HMI        Speech   Position   Distance
                                  │           │
                                  ▼           ▼
                              Center       Distance
                             Controller   Controller
                                  │           │
                                  └─────┬─────┘
                                        ▼
                                  Follow Control
                                        │
                                        ▼
                                 Differential Drive
                                        │
                                  ┌─────┴─────┐
                                  ▼           ▼
                                V_left      V_right
                                  │           │
                                  └─────┬─────┘
                                        ▼
                                       UART
                                        │
                                        ▼
                                      ESP32
                                        │
                                  ┌─────┴─────┐
                                  ▼           ▼
                                Left        Right
                                 PID          PID
                                  │           │
                                  ▼           ▼
                                Motor       Motor
                                  │           │
                                  ▼           ▼
                               Encoder     Encoder
                                  │           │
                                  └─────┬─────┘
                                        ▼
                                     Feedback
```

The fundamental NEXUS data pipeline is therefore:

> **Sense → Detect → Track → Associate → Authenticate → Lock Target → Determine State → Control → Convert to Wheel Commands → Communicate → PID → Actuate → Feedback.**
