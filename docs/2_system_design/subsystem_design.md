
# NEXUS Subsystem Design

## 1. Purpose

This document defines the functional subsystems of the NEXUS robot and establishes the responsibility and boundary of each subsystem.

The purpose is to ensure that every system function has a clear owner before software implementation begins.

This document defines:

* Functional subsystems
* Responsibilities
* Inputs and outputs
* Dependencies
* Processing behavior
* Subsystem boundaries
* Interaction between Raspberry Pi and ESP32

Detailed class definitions, function interfaces, and implementation-specific code are defined in the software design documents.

---

# 2. System Decomposition

NEXUS is divided into the following major subsystems:

```text
NEXUS
│
├── 1. Perception Subsystem
│   ├── Camera
│   ├── Person Detection
│   ├── Person Tracking
│   └── Gesture Recognition
│
├── 2. Target Management Subsystem
│   ├── Proximity Management
│   ├── Gesture-Person Association
│   ├── Authentication
│   └── Target Management
│
├── 3. Robot State Subsystem
│   └── State Machine
│
├── 4. Follow Control Subsystem
│   ├── Center Controller
│   ├── Distance Controller
│   ├── Follow Controller
│   └── Differential Drive
│
├── 5. Communication Subsystem
│   └── Raspberry Pi ↔ ESP32 UART
│
├── 6. HMI Subsystem
│   ├── Live Camera
│   ├── Robot Face
│   └── HMI Manager
│
├── 7. Speech Subsystem
│   └── Speech Manager
│
└── 8. Low-Level Motor Control Subsystem
    ├── UART Command Parser
    ├── Encoder
    ├── PID
    ├── PWM
    └── Motor Control
```

---

# 3. Subsystem Ownership

The following table defines which processor owns each subsystem.

| Subsystem               | Raspberry Pi | ESP32 |
| ----------------------- | :----------: | :---: |
| Camera                  |      ✓      |      |
| Person Detection        |      ✓      |      |
| Person Tracking         |      ✓      |      |
| Gesture Recognition     |      ✓      |      |
| Proximity Management    |      ✓      |      |
| Authentication          |      ✓      |      |
| Target Management       |      ✓      |      |
| State Machine           |      ✓      |      |
| Follow Controller       |      ✓      |      |
| Differential Drive      |      ✓      |      |
| HMI                     |      ✓      |      |
| Speech                  |      ✓      |      |
| UART Communication      |      ✓      |  ✓  |
| Encoder Reading         |              |  ✓  |
| Wheel-Speed Measurement |              |  ✓  |
| PID Control             |              |  ✓  |
| PWM                     |              |  ✓  |
| Motor Driver Control    |              |  ✓  |
| Communication Timeout   |              |  ✓  |

The Raspberry Pi is responsible for **what the robot should do**.

The ESP32 is responsible for **how the motors physically execute the command**.

---

# 4. Perception Subsystem

## 4.1 Purpose

The Perception Subsystem converts raw camera data into structured information about:

* People
* Person locations
* Person identities/tracking IDs
* Hand gestures

It is the primary input subsystem for NEXUS's high-level intelligence.

---

# 5. Camera Subsystem

## Purpose

Capture image frames for all vision-based functions.

## Responsibilities

* Initialize the camera
* Configure resolution
* Configure frame rate
* Capture frames
* Provide frames to vision modules
* Handle camera errors

## Inputs

```text
Camera hardware
```

## Outputs

```text
Image Frame
```

## Consumers

* Person Detection
* Gesture Recognition
* Live Camera HMI

## Ownership

```text
Raspberry Pi
```

## Important Boundary

The Camera subsystem only provides images.

It does not:

* Detect people
* Recognize gestures
* Select targets
* Control motors

---

# 6. Person Detection Subsystem

## Purpose

Detect people appearing in the camera frame.

## Responsibilities

* Run person detection model
* Detect human bounding boxes
* Calculate detection confidence
* Filter detections based on configured thresholds

## Input

```text
Image Frame
```

## Output

Conceptually:

```text
PersonDetection
├── bounding_box
├── confidence
└── class
```

## Example

```text
PersonDetection:
    bbox = [x1, y1, x2, y2]
    confidence = 0.91
    class = PERSON
```

## Dependencies

* Camera
* Object detection model
* OpenCV / vision framework

## Does NOT handle

* Persistent IDs
* Target selection
* Password validation
* Motor control

---

# 7. Person Tracking Subsystem

## Purpose

Maintain persistent identities for detected people across frames.

## Responsibilities

* Associate detections across frames
* Assign tracking IDs
* Maintain bounding boxes
* Handle temporary disappearance
* Report active tracks
* Report lost tracks

## Input

```text
PersonDetection[]
```

## Output

```text
TrackedPerson[]
```

Conceptually:

```text
TrackedPerson
├── track_id
├── bounding_box
├── center
├── confidence
└── tracking_status
```

Example:

```text
Track ID 3
    bbox = [250, 100, 450, 600]
    center = [350, 350]
    status = ACTIVE
```

## Dependencies

* Person Detection

## Candidate implementation

A tracker such as:

* ByteTrack
* BoT-SORT

may be used.

The tracking algorithm should be replaceable without changing the Target Manager interface.

---

# 8. Gesture Recognition Subsystem

## Purpose

Detect the predefined password gesture.

## Responsibilities

* Detect hands
* Extract hand landmarks/features
* Classify gesture
* Return gesture confidence
* Report gesture position

## Input

```text
Image Frame
```

## Output

Conceptually:

```text
GestureDetection
├── gesture_type
├── confidence
├── hand_position
└── bounding_box
```

## Example

```text
gesture_type = PASSWORD
confidence = 0.94
```

## Important Boundary

Gesture Recognition determines:

> "What gesture is being performed?"

It does **not** determine:

> "Who performed the gesture?"

That responsibility belongs to Gesture-Person Association.

---

# 9. Gesture-Person Association Subsystem

## Purpose

Determine which tracked person performed a detected gesture.

This subsystem is critical because the password is associated with a person.

## Input

```text
TrackedPerson[]
+
GestureDetection[]
```

## Output

```text
gesture_person_id
```

Example:

```text
Tracked persons:
    ID 1
    ID 2
    ID 5

Detected password gesture:
    position = [520, 300]

Associated person:
    ID 5
```

## Possible association strategy

Use spatial relationships between:

* Hand bounding box
* Hand center
* Person bounding box

For example:

```text
Hand Center
     ↓
Which person bounding box contains
or is closest to the hand?
     ↓
Associated Track ID
```

The exact association algorithm can be refined during implementation.

---

# 10. Proximity Management Subsystem

## Purpose

Determine whether a person is sufficiently close to NEXUS to trigger the greeting.

## Inputs

```text
Person Tracks
+
Distance Sensor
```

## Output

```text
person_nearby
greeting_candidate
```

## Responsibilities

* Measure distance
* Determine whether a person is within greeting range
* Select a suitable nearby person if multiple people exist
* Prevent repeated greetings
* Reset greeting eligibility when the interaction ends

## Greeting logic

```text
Person detected
      +
Within GREETING_DISTANCE
      +
Greeting allowed
      ↓
Greeting event
```

## Important Boundary

Proximity detection does not activate the robot.

It only generates a greeting event.

---

# 11. Authentication Subsystem

## Purpose

Determine whether a detected gesture is a valid password and determine the authenticated person.

## Inputs

```text
Gesture Detection
+
Associated Track ID
+
Current Robot State
```

## Output

```text
Authentication Result
├── valid / invalid
├── person_id
└── authentication_event
```

## OFF behavior

```text
Valid Password
      ↓
Authentication SUCCESS
      ↓
Person becomes candidate target
```

## FOLLOW behavior

```text
Valid Password
      ↓
Check gesture_person_id
      ↓
Is ID == target_id?
```

If yes:

```text
Deactivate
```

If no:

```text
Ignore
```

---

# 12. Target Management Subsystem

## Purpose

Manage the identity and tracking state of the currently locked target.

## Responsibilities

* Lock target
* Store target ID
* Update target position
* Update target distance
* Determine target visibility
* Detect target loss
* Clear target
* Prevent unauthorized target switching

## Input

```text
TrackedPerson[]
+
Authentication Result
+
Distance Data
```

## Output

```text
Target
```

Conceptually:

```text
Target
├── track_id
├── bounding_box
├── center
├── distance
├── visible
└── tracking_status
```

---

# 13. Target Lock

When authentication succeeds in `OFF`:

```text
Authenticated Person ID
        ↓
Target Manager
        ↓
target_id = authenticated_person_id
```

Once locked:

```text
target_id
```

must remain unchanged until:

* The target explicitly deactivates NEXUS
* The target is lost beyond timeout
* A critical system reset occurs

NEXUS must not switch targets merely because another person becomes closer.

---

# 14. Target Loss Management

The Target Manager detects whether the locked target remains trackable.

```text
Target visible
     ↓
Normal FOLLOW
```

If the target disappears:

```text
Target not visible
     ↓
Start loss timer
```

If the target returns:

```text
Cancel loss timer
Continue FOLLOW
```

If timeout expires:

```text
Clear target
Stop robot
Return OFF
```

---

# 15. Robot State Subsystem

## Purpose

Control the global behavioral state of NEXUS.

## States

```text
OFF
GREETING
TARGET_LOCK
FOLLOW
DEACTIVATING
ERROR
```

## Inputs

The state machine receives events such as:

```text
PERSON_NEARBY
GREETING_COMPLETE
VALID_PASSWORD
INVALID_PASSWORD
TARGET_LOCKED
TARGET_LOST
TARGET_REACQUIRED
TARGET_LOST_TIMEOUT
TARGET_DEACTIVATION
SYSTEM_ERROR
```

## Outputs

The state machine determines:

* Current state
* Allowed actions
* HMI mode
* Speech events
* Motor permission
* Target management behavior

The detailed transition rules are defined in `state_machine.md`.

---

# 16. Center Controller

## Purpose

Control robot orientation based on target horizontal position.

## Input

Target bounding box.

For image width \(W\):

$$
x_{camera}=\frac{W}{2}
$$

For target bounding box:

$$
x_c=\frac{x_1+x_2}{2}
$$

Horizontal error:

$$
e_x=x_c-x_{camera}
$$

## Output

```text
Angular velocity ω
```

## Behavior

```text
Target left
    ↓
Turn left

Target centered
    ↓
ω ≈ 0

Target right
    ↓
Turn right
```

The exact controller may use proportional control initially:

$$
\omega = K_x e_x
$$

with saturation limits.

---

# 17. Distance Controller

## Purpose

Control robot linear motion based on target distance.

## Input

```text
Measured distance D_person
Desired distance D_target
```

Error:

$$
e_d=D_{person}-D_{target}
$$

## Output

```text
Linear velocity V
```

## Initial behavior

```text
Target too far
    ↓
Move forward

Target at desired distance
    ↓
Stop / slow

Target too close
    ↓
Stop
```

Reverse movement should initially remain disabled until safety testing is complete.

---

# 18. Follow Controller

## Purpose

Combine orientation and distance control.

## Inputs

```text
Horizontal target error
Target distance
Robot configuration
```

## Outputs

```text
V
ω
```

Conceptually:

```text
             Target
                │
       ┌────────┴────────┐
       ▼                 ▼
 Horizontal Error    Distance Error
       │                 │
       ▼                 ▼
 Center Controller  Distance Controller
       │                 │
       ▼                 ▼
       ω                 V
        \               /
         \             /
          ▼           ▼
           Follow Controller
```

The Follow Controller is responsible for combining these control outputs and enforcing overall velocity limits.

---

# 19. Differential Drive Subsystem

## Purpose

Convert robot-level velocity commands into individual wheel velocities.

## Input

```text
V
ω
```

## Output

```text
V_left
V_right
```

Using:

$$
V_L=V-\frac{\omega W}{2}
$$

$$
V_R=V+\frac{\omega W}{2}
$$

where \(W\) is the distance between the rear drive wheels.

The front caster does not receive a control command.

---

# 20. Communication Subsystem

## Purpose

Provide reliable communication between Raspberry Pi and ESP32.

## Responsibilities

* Send wheel commands
* Receive ESP32 status
* Detect communication problems
* Validate received data
* Provide communication status

## Raspberry Pi → ESP32

Conceptually:

```text
V_left
V_right
```

## ESP32 → Raspberry Pi

Conceptually:

```text
Encoder information
Motor status
Error status
```

The detailed packet format is defined in `communication_protocol.md`.

---

# 21. HMI Subsystem

## Purpose

Provide visual feedback to users.

## Modes

### OFF

```text
Live Camera
```

### GREETING

```text
Greeting animation
```

### TARGET_LOCK

```text
Activation animation
```

### FOLLOW

```text
Robot face
```

### Target Lost

```text
Warning / Lost expression
```

### DEACTIVATING

```text
Goodbye animation
```

### ERROR

```text
Error screen
```

The HMI must reflect the robot state and must not make independent decisions about robot behavior.

---

# 22. Speech Subsystem

## Purpose

Provide voice feedback and interaction.

## Responsibilities

* Play predefined speech
* Manage speech cooldowns
* Prevent repeated speech
* Queue or reject non-critical speech events
* Avoid blocking safety-critical operations

## Events

```text
GREETING
ACTIVATED
TARGET_LOCKED
FOLLOWING
TARGET_LOST
TARGET_LOST_TIMEOUT
DEACTIVATED
ERROR
```

Speech is subordinate to motor safety.

---

# 23. ESP32 Low-Level Motor Control Subsystem

## Purpose

Provide deterministic closed-loop control of the two rear drive motors.

## Components

```text
UART Parser
     ↓
Command Processor
     ↓
Wheel Command
     ↓
PID Controller
     ↓
PWM
     ↓
Motor Driver
     ↓
Motor
     ↓
Encoder
     ↓
Feedback
     ↓
PID
```

---

# 24. Encoder Subsystem

## Purpose

Measure rear wheel rotation.

## Inputs

```text
Left encoder
Right encoder
```

## Outputs

```text
Left wheel speed
Right wheel speed
```

The encoder subsystem belongs entirely to the ESP32.

---

# 25. PID Motor Controller

## Purpose

Make each motor achieve its commanded wheel velocity.

Each wheel has an independent PID controller.

```text
Left command
    ↓
Left PID
    ↓
Left PWM
    ↓
Left Motor
    ↓
Left Encoder
    └──────► feedback

Right command
    ↓
Right PID
    ↓
Right PWM
    ↓
Right Motor
    ↓
Right Encoder
    └──────► feedback
```

The PID loop operates independently of the Raspberry Pi vision processing.

---

# 26. Communication Timeout Safety

The ESP32 must implement a communication watchdog.

If valid commands are not received within the configured timeout:

```text
UART timeout
     ↓
Command invalidated
     ↓
Left motor STOP
Right motor STOP
```

The ESP32 must not continue executing an old movement command indefinitely.

---

# 27. Subsystem Dependency Matrix

| Subsystem                  | Depends On                           |
| -------------------------- | ------------------------------------ |
| Camera                     | Camera hardware                      |
| Person Detection           | Camera                               |
| Person Tracking            | Person Detection                     |
| Gesture Recognition        | Camera                               |
| Gesture-Person Association | Tracking + Gesture                   |
| Proximity Manager          | Tracking + Distance Sensor           |
| Authentication             | Gesture + Association + State        |
| Target Manager             | Tracking + Authentication + Distance |
| State Machine              | Events from multiple subsystems      |
| Center Controller          | Target Manager                       |
| Distance Controller        | Target Manager / Distance Sensor     |
| Follow Controller          | Center + Distance Controllers        |
| Differential Drive         | Follow Controller                    |
| UART                       | Differential Drive                   |
| PID                        | UART + Encoder                       |
| Motor Control              | PID + Motor Driver                   |
| HMI                        | Robot State                          |
| Speech                     | Robot Events / Robot State           |

---

# 28. Subsystem Boundary Rules

The following boundaries must be maintained.

### Perception must not control motors

```text
Person Detection
       X
       ↓
Motor
```

Instead:

```text
Perception
    ↓
Target Manager
    ↓
Follow Controller
    ↓
Motor Command
```

### ESP32 must not perform high-level perception

```text
ESP32
    X
Person Detection
Gesture Recognition
Target Selection
```

### HMI must not control robot behavior

The HMI displays state; it does not determine state.

### Speech must not block control

Speech execution must be asynchronous or otherwise non-blocking.

### Target Manager owns target identity

No other subsystem should independently change `target_id`.

---

# 29. Subsystem Interaction Summary

The complete logical relationship is:

```text
              ┌─────────────────────┐
              │      CAMERA         │
              └──────────┬──────────┘
                         │
               ┌─────────┴─────────┐
               ▼                   ▼
       Person Detection      Gesture Recognition
               │                   │
               ▼                   │
       Person Tracking             │
               │                   │
               └────────┬──────────┘
                        ▼
              Gesture-Person Association
                        │
                        ▼
                 Authentication
                        │
                        ▼
                 Target Manager
                        │
                        ▼
                  State Machine
                        │
                        ▼
                 Follow Controller
                   ┌────┴────┐
                   ▼         ▼
              Center      Distance
             Controller   Controller
                   │         │
                   └────┬────┘
                        ▼
                Differential Drive
                        │
                        ▼
                       UART
                        │
                        ▼
                      ESP32
                  ┌─────┴─────┐
                  ▼           ▼
                Left        Right
                PID          PID
                  │           │
                  ▼           ▼
               Motor       Motor
```

---

# 30. Design Summary

NEXUS uses a layered subsystem architecture:

```text
Layer 1 — Perception
    Camera
    Detection
    Tracking
    Gesture

Layer 2 — Intelligence
    Authentication
    Target Management
    State Machine

Layer 3 — Motion Planning / Control
    Center Control
    Distance Control
    Follow Control
    Differential Drive

Layer 4 — Communication
    Raspberry Pi ↔ ESP32

Layer 5 — Real-Time Actuation
    Encoder
    PID
    PWM
    Motors

Parallel Layer — User Interface
    HMI
    Speech
```

The architecture ensures that:

> **Perception identifies what is happening, intelligence decides what NEXUS should do, control determines how it should move, and the ESP32 executes the motor commands safely.**
