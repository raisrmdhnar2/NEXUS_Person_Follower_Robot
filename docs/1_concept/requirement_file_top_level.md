# NEXUS Python File Architecture

## 1. Purpose

This document defines the recommended Python file structure required to implement the **NEXUS top-level architecture** on the Raspberry Pi.

The software architecture follows this main pipeline:

```text
Camera
  │
  ▼
Person Detection
  │
  ▼
Person Tracking
  │
  ├───────────────┐
  │               ▼
  │        Proximity Detection
  │               │
  │               ▼
  │          Greeting Manager
  │
  ├───────────────┐
  │               ▼
  │       Gesture Recognition
  │               │
  └───────┬───────┘
          ▼
    Authentication
          │
          ▼
      Target Lock
          │
          ▼
    Target Tracking
          │
     ┌────┴────┐
     ▼         ▼
Target Center  Distance
     │         │
     └────┬────┘
          ▼
   Follow Controller
          │
          ▼
        V, ω
          │
          ▼
 Differential Drive
          │
     ┌────┴────┐
     ▼         ▼
   V_left    V_right
     │         │
     └────┬────┘
          ▼
        UART
          │
          ▼
        ESP32
```

The Raspberry Pi handles:

* Computer vision.
* Person detection.
* Person tracking.
* Gesture recognition.
* Person proximity detection.
* Authentication.
* Target locking.
* Follow control.
* Differential-drive calculation.
* HMI.
* Speech.
* Communication with ESP32.

The ESP32 handles:

* Encoder reading.
* Motor PID.
* PWM generation.
* Motor driver control.
* Communication timeout.

---

# 2. Recommended Python Directory Structure

```text
raspberry_pi/
│
├── main.py
├── config.py
│
├── state.py
│
├── vision/
│   ├── __init__.py
│   ├── camera.py
│   ├── person_detection.py
│   ├── person_tracking.py
│   └── gesture_recognition.py
│
├── target/
│   ├── __init__.py
│   ├── target_manager.py
│   └── proximity_manager.py
│
├── sensors/
│   ├── __init__.py
│   └── distance_sensor.py
│
├── control/
│   ├── __init__.py
│   ├── center_controller.py
│   ├── distance_controller.py
│   ├── follow_controller.py
│   └── differential_drive.py
│
├── communication/
│   ├── __init__.py
│   └── esp32_uart.py
│
├── ui/
│   ├── __init__.py
│   ├── hmi_manager.py
│   ├── live_camera.py
│   ├── robot_face.py
│   └── speech_manager.py
│
└── utils/
    ├── __init__.py
    └── logger.py
```

Ignoring the `__init__.py` files, this architecture contains approximately **19 functional Python files**.

Not all files need to be implemented at the beginning.

---

# 3. `main.py`

## Purpose

`main.py` is the main entry point of the NEXUS application.

It coordinates all subsystems but should contain as little low-level implementation logic as possible.

Its primary responsibility is to run the main robot loop.

---

## Responsibilities

`main.py` should:

* Initialize all modules.
* Start the camera.
* Initialize person detection.
* Initialize tracking.
* Initialize gesture recognition.
* Initialize the distance sensor.
* Initialize UART communication.
* Initialize HMI and speech.
* Maintain the robot state.
* Execute the perception-control loop.
* Send motor commands to ESP32.
* Handle clean shutdown.

---

## Conceptual Logic

```python
while running:

    frame = camera.read()

    detections = person_detector.detect(frame)

    tracks = tracker.update(detections)

    gesture = gesture_recognizer.detect(frame)

    distance = distance_sensor.read()

    robot_state = state_manager.update(
        tracks,
        gesture,
        distance
    )

    if robot_state == FOLLOW:

        target = target_manager.get_target(tracks)

        v, omega = follow_controller.update(
            target,
            distance
        )

        left, right = differential_drive.calculate(
            v,
            omega
        )

        uart.send_velocity(left, right)

    else:

        uart.stop()

    hmi.update(robot_state, frame)
```

---

# 4. `config.py`

## Purpose

`config.py` stores all important configurable system parameters.

Avoid hardcoding parameters inside multiple files.

---

## Example Parameters

```python
CAMERA_INDEX = 0

CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480

GREETING_DISTANCE = 2.0

TARGET_DISTANCE = 1.2

TARGET_LOST_TIMEOUT = 1.5

MAX_LINEAR_SPEED = 0.5

MAX_ANGULAR_SPEED = 1.0

WHEEL_BASE = 0.45

UART_PORT = "/dev/ttyUSB0"

UART_BAUDRATE = 115200
```

---

## Why This File Is Important

During robot testing, parameters such as:

* Distance thresholds.
* PID values.
* Maximum speed.
* UART settings.
* Camera resolution.

will change frequently.

Keeping them in one file makes calibration much easier.

---

# 5. `state.py`

## Purpose

Defines the robot operating states.

Example:

```python
from enum import Enum

class RobotState(Enum):
    OFF = 0
    GREETING = 1
    TARGET_LOCK = 2
    FOLLOW = 3
    DEACTIVATING = 4
    ERROR = 5
```

This prevents state names from being duplicated as raw strings throughout the project.

---

# 6. `vision/camera.py`

## Purpose

Handles camera initialization and frame acquisition.

---

## Responsibilities

* Initialize camera.
* Configure resolution.
* Read frames.
* Detect camera failure.
* Release camera resources.

---

## Example Interface

```python
camera = Camera()

frame = camera.read()

camera.release()
```

---

## Data Flow

```text
Physical Camera
      │
      ▼
camera.py
      │
      ▼
OpenCV Frame
      │
      ├── Person Detection
      ├── Gesture Recognition
      └── Live Camera HMI
```

---

# 7. `vision/person_detection.py`

## Purpose

Detect people inside each camera frame.

A YOLO-based detector can be used for this module.

---

## Input

```text
Camera frame
```

---

## Output

A list of detected people.

Example:

```python
[
    {
        "bbox": [100, 80, 300, 450],
        "confidence": 0.92
    }
]
```

---

## Responsibilities

* Run object detection.
* Filter only the `person` class.
* Apply confidence threshold.
* Return person bounding boxes.

---

## Data Flow

```text
Camera Frame
     │
     ▼
Person Detector
     │
     ▼
Bounding Boxes
```

---

# 8. `vision/person_tracking.py`

## Purpose

Assign and maintain IDs for detected people across frames.

Possible trackers:

* ByteTrack.
* BoT-SORT.

---

## Example

Frame 1:

```text
Person A → ID 1
Person B → ID 2
```

Frame 2:

```text
Person A → ID 1
Person B → ID 2
```

The IDs should remain stable while the tracker can confidently maintain identity.

---

## Output Example

```python
[
    {
        "track_id": 1,
        "bbox": [80, 70, 280, 440]
    },
    {
        "track_id": 2,
        "bbox": [330, 90, 520, 450]
    }
]
```

---

# 9. `vision/gesture_recognition.py`

## Purpose

Detect the predefined password hand gesture.

Possible implementation:

* MediaPipe Hands.
* Custom gesture classifier.
* Rule-based finger state recognition.

---

## Output Example

```python
{
    "gesture": "PASSWORD",
    "hand_center": [320, 210]
}
```

or:

```python
None
```

if no valid gesture is detected.

---

## Important Requirement

The gesture itself is not enough.

The gesture must later be associated with the person who performed it.

---

# 10. `target/proximity_manager.py`

## Purpose

Determine whether a person is close enough to trigger the NEXUS welcome greeting.

This module is used while NEXUS is in the `OFF` state.

---

## Main Logic

```text
Person detected
      │
      ▼
Distance measured
      │
      ▼
Distance < Greeting Threshold?
      │
   ┌──┴───┐
  NO     YES
  │        │
  │        ▼
  │    Trigger Greeting
  │
  ▼
Continue monitoring
```

---

## Responsibilities

* Detect whether a person is nearby.
* Determine whether greeting conditions are met.
* Prevent repeated greetings.
* Reset greeting permission when the person leaves.
* Apply greeting cooldown if needed.

---

## Example Interface

```python
should_greet = proximity_manager.update(
    persons,
    distance
)
```

---

# 11. `target/target_manager.py`

## Purpose

`target_manager.py` is one of the most important modules in the project.

It manages:

* Authentication.
* Target locking.
* Target ID.
* Target loss.
* Deactivation.
* Gesture-to-person association.

---

## Main Responsibilities

### Activation

```text
Valid Gesture
      │
      ▼
Find Person
Associated With Gesture
      │
      ▼
Obtain Tracking ID
      │
      ▼
Target ID = Tracking ID
```

---

### Following

If:

```text
Target ID = 4
```

NEXUS follows only:

```text
Track ID 4
```

---

### Deactivation

When the valid gesture is detected during `FOLLOW`:

```text
Gesture
   │
   ▼
Which person performed it?
   │
   ▼
Person ID == Target ID?
   │
 ┌─┴─┐
NO  YES
│     │
│     ▼
│  DEACTIVATE
│
▼
Ignore
```

---

### Target Loss

```text
Target disappears
      │
      ▼
Start target-lost timer
      │
      ├── Target returns
      │       ↓
      │   Continue FOLLOW
      │
      └── Timeout
              ↓
         DEACTIVATE
```

---

## Example Interface

```python
target_manager.lock_target(track_id)

target = target_manager.get_target(tracks)

target_manager.clear_target()

lost = target_manager.is_target_lost(tracks)
```

---

# 12. `sensors/distance_sensor.py`

## Purpose

Read the target/person distance.

The exact implementation depends on the selected sensor.

---

## Responsibilities

* Initialize the distance sensor.
* Read distance.
* Filter noisy readings.
* Detect invalid measurements.
* Return distance in a consistent unit.

Recommended unit:

```text
meters
```

---

## Example Interface

```python
distance = distance_sensor.read()
```

Example output:

```python
1.45
```

meaning:

```text
1.45 meters
```

---

# 13. `control/center_controller.py`

## Purpose

Calculate the angular velocity command needed to keep the target in the center of the camera.

---

## Input

Target bounding-box center:

$$
x_c
$$

Camera center:

$$
x_{camera}
$$

Error:

$$
e_x = x_c - x_{camera}
$$

---

## Output

Angular velocity:

$$
\omega
$$

---

## Example Logic

```text
Target Left
    ↓
ω < 0

Target Center
    ↓
ω ≈ 0

Target Right
    ↓
ω > 0
```

The exact sign convention must be consistent with the differential-drive implementation.

---

# 14. `control/distance_controller.py`

## Purpose

Calculate the robot's forward velocity based on target distance.

---

## Distance Error

$$
e_d = D_{person} - D_{target}
$$

where:

* \(D_{person}\) = measured distance.
* \(D_{target}\) = desired following distance.

---

## Basic Behavior

```text
Target too far
      ↓
Move forward

Target at desired distance
      ↓
Stop

Target too close
      ↓
Stop
```

For the first prototype, backward motion can be disabled for safety.

---

## Output

Linear velocity:

$$
V
$$

---

# 15. `control/follow_controller.py`

## Purpose

Combine center control and distance control.

---

## Input

```text
Target bounding box
Target distance
```

---

## Output

```text
V
ω
```

---

## Internal Flow

```text
Target Bounding Box
       │
       ▼
Center Controller
       │
       ▼
       ω


Target Distance
       │
       ▼
Distance Controller
       │
       ▼
       V
```

Then:

```text
V + ω
  │
  ▼
Follow Controller Output
```

---

# 16. `control/differential_drive.py`

## Purpose

Convert robot-level motion commands:

$$
V,\omega
$$

into wheel velocity commands:

$$
V_L,V_R
$$

---

## Equations

$$
V_L = V - \frac{\omega W}{2}
$$

$$
V_R = V + \frac{\omega W}{2}
$$

where:

* \(V_L\) = left rear wheel velocity.
* \(V_R\) = right rear wheel velocity.
* \(W\) = wheel separation.
* \(V\) = robot linear velocity.
* \(\omega\) = robot angular velocity.

---

## Example Interface

```python
left, right = differential_drive.calculate(
    linear_velocity,
    angular_velocity
)
```

---

## Important Design Rule

This file should contain only mathematical drive calculations.

It should not:

* Access camera.
* Read sensors.
* Send UART.
* Perform tracking.

This makes it easy to test independently.

---

# 17. `communication/esp32_uart.py`

## Purpose

Manage communication between Raspberry Pi and ESP32.

---

## Responsibilities

* Open serial connection.
* Send left-wheel velocity.
* Send right-wheel velocity.
* Send STOP command.
* Optionally read ESP32 status.
* Detect communication errors.

---

## Example

```python
uart.send_velocity(
    left=0.25,
    right=0.31
)
```

---

## Possible UART Packet

```text
VEL,0.25,0.31
```

or:

```text
LEFT:0.25,RIGHT:0.31
```

The exact protocol should be documented separately.

---

# 18. `ui/hmi_manager.py`

## Purpose

Determine what should be displayed on the NEXUS monitor according to the current state.

---

## State Mapping

```text
OFF
 ↓
Live Camera

GREETING
 ↓
Greeting Animation

TARGET_LOCK
 ↓
Hello Animation

FOLLOW
 ↓
Robot Face

TARGET LOST
 ↓
Lost / Confused Face

DEACTIVATING
 ↓
Goodbye Animation

ERROR
 ↓
Error Screen
```

---

## Example Interface

```python
hmi_manager.update(
    robot_state,
    frame
)
```

---

# 19. `ui/live_camera.py`

## Purpose

Display the camera feed on the physical NEXUS monitor.

This is primarily used while NEXUS is `OFF`.

---

## Data Flow

```text
Camera
   │
   ▼
Frame
   │
   ▼
Live Camera UI
   │
   ▼
HDMI Monitor
```

---

# 20. `ui/robot_face.py`

## Purpose

Display NEXUS's face and animations.

---

## Possible Expressions

### Normal

```text
(•‿•)
```

### Happy

```text
(^‿^)
```

### Target Lost

```text
(•︵•)
```

### Confused

```text
(⊙_⊙)
```

### Error

```text
(×_×)
```

---

## Future Development

This module can later be expanded into:

* Animated eyes.
* Blinking.
* Mouth animation.
* Emotion transitions.
* Speech-synchronized mouth movement.

---

# 21. `ui/speech_manager.py`

## Purpose

Manage all NEXUS voice output.

---

## Speech Events

### Nearby Person

```text
“Welcome to the Technology and Information Department of Brawijaya University!
Hello! I’m NEXUS. I’m ready to follow you.
Please show me the password.”
```

### Password Accepted

```text
“Hello! Nice to see you.”
```

### Target Locked

```text
“I’ll follow you.”
```

### Normal Following

```text
“I’m right behind you.”
```

### Temporary Target Loss

```text
“Where are you?”
```

### Target Loss Timeout

```text
“I can’t find you.”
```

### Deactivation

```text
“Okay! See you later!”
```

### Error

```text
“Something went wrong.”
```

---

## Responsibilities

`speech_manager.py` should:

* Load audio files.
* Play predefined voice lines.
* Avoid repeated speech.
* Implement cooldowns.
* Trigger speech according to events.
* Allow safety-critical actions to interrupt speech.

---

## Recommended Interface

```python
speech.say("welcome")
```

```python
speech.say("target_locked")
```

```python
speech.say("target_lost")
```

```python
speech.say("goodbye")
```

---

# 22. `utils/logger.py`

## Purpose

Provide centralized logging.

This is very useful during robot development.

---

## Example Logs

```text
[INFO] Camera initialized

[INFO] Person detected: ID=4

[INFO] Greeting triggered

[INFO] Password gesture detected

[INFO] Target locked: ID=4

[INFO] FOLLOW mode

[DEBUG] Distance = 1.63 m

[DEBUG] V = 0.21 m/s

[DEBUG] Omega = -0.15 rad/s

[WARNING] Target temporarily lost

[ERROR] ESP32 communication timeout
```

---

## Why Logging Is Important

Without logging, debugging a robot with:

* Vision.
* Tracking.
* Sensors.
* Motors.
* UART.
* State machine.

becomes very difficult.

---

# 23. Module Relationship

The recommended module relationship is:

```text
                         main.py
                           │
        ┌──────────────────┼───────────────────┐
        │                  │                   │
        ▼                  ▼                   ▼
      Vision             Target              HMI
        │                  │                   │
        │                  │                   │
 camera.py          target_manager.py   hmi_manager.py
        │           proximity_manager.py       │
        │                  │             ┌─────┴─────┐
        ▼                  │             ▼           ▼
person_detection.py        │      live_camera.py speech_manager.py
        │                  │
        ▼                  │
person_tracking.py         │
        │                  │
gesture_recognition.py─────┘
                           │
                           ▼
                     Follow Control
                           │
                ┌──────────┴──────────┐
                ▼                     ▼
       center_controller.py   distance_controller.py
                │                     │
                └──────────┬──────────┘
                           ▼
                follow_controller.py
                           │
                           ▼
               differential_drive.py
                           │
                           ▼
                    esp32_uart.py
                           │
                           ▼
                         ESP32
```

---

# 24. Robot State Flow

The primary software state flow should be:

```text
POWER ON
    │
    ▼
INITIALIZATION
    │
    ▼
OFF
    │
    ├── No nearby person
    │       ↓
    │    Stay OFF
    │
    └── Person nearby
            ↓
         GREETING
            ↓
           OFF
            │
       Valid Password
            │
            ▼
       TARGET_LOCK
            │
            ▼
          FOLLOW
            │
       ┌────┴─────────────┐
       │                  │
Target Lost       Password from Target
       │                  │
       ▼                  ▼
Loss Timer          DEACTIVATE
       │                  │
   ┌───┴────┐             │
   │        │             │
Return   Timeout          │
   │        │             │
   ▼        ▼             │
FOLLOW  DEACTIVATE ◀──────┘
             │
             ▼
            OFF
```

---

# 25. Recommended Development Order

Do not implement all modules simultaneously.

The project should be implemented incrementally.

---

## Phase 1 — Camera and Person Detection

Files:

```text
main.py
config.py
vision/camera.py
vision/person_detection.py
```

Goal:

```text
Camera
  ↓
Person Detection
  ↓
Bounding Box Display
```

At this stage, NEXUS should only detect people.

---

## Phase 2 — Person Tracking

Add:

```text
vision/person_tracking.py
```

Goal:

```text
Person Detection
       ↓
Person Tracking
       ↓
Persistent Track IDs
```

Example:

```text
Person → ID 1
Person → ID 2
```

---

## Phase 3 — Basic Following

Add:

```text
sensors/distance_sensor.py

control/center_controller.py
control/distance_controller.py
control/follow_controller.py
control/differential_drive.py

communication/esp32_uart.py
```

Goal:

```text
Target
  │
  ├── Position
  └── Distance
        │
        ▼
       V, ω
        │
        ▼
    V_left/V_right
        │
        ▼
       ESP32
        │
        ▼
       Motors
```

At this point NEXUS should physically follow a selected person.

---

## Phase 4 — Gesture Password

Add:

```text
vision/gesture_recognition.py
target/target_manager.py
state.py
```

Goal:

```text
Gesture
   ↓
Password
   ↓
Person Association
   ↓
Target ID
   ↓
FOLLOW
```

---

## Phase 5 — Greeting

Add:

```text
target/proximity_manager.py
ui/speech_manager.py
```

Goal:

```text
Person nearby
    ↓
Greeting Trigger
    ↓
NEXUS Says Welcome Message
    ↓
Wait for Password
```

---

## Phase 6 — Monitor HMI

Add:

```text
ui/hmi_manager.py
ui/live_camera.py
ui/robot_face.py
```

Goal:

```text
OFF
 ↓
Live Camera

GREETING
 ↓
Greeting UI

FOLLOW
 ↓
Robot Face
```

---

## Phase 7 — Safety and Refinement

Add or improve:

```text
utils/logger.py
```

Optional future modules:

```text
safety_manager.py
diagnostics.py
audio_manager.py
event_manager.py
```

Goal:

* Communication safety.
* Target-loss handling.
* Reliable logs.
* Error handling.
* Clean shutdown.
* Stable real-time operation.

---

# 26. Minimum Files for First Prototype

The first functional prototype does not require the complete architecture.

Recommended minimum:

```text
raspberry_pi/
│
├── main.py
├── config.py
│
├── vision/
│   ├── camera.py
│   ├── person_detection.py
│   └── person_tracking.py
│
├── sensors/
│   └── distance_sensor.py
│
├── control/
│   ├── follow_controller.py
│   └── differential_drive.py
│
└── communication/
    └── esp32_uart.py
```

Total:

**9 main Python files**

The first milestone is:

```text
Person detected
      ↓
Person tracked
      ↓
Position calculated
      ↓
Distance measured
      ↓
Follow command calculated
      ↓
V_left and V_right
      ↓
ESP32
      ↓
Robot moves
```

---

# 27. Full Recommended Implementation

For the complete NEXUS concept:

```text
main.py

config.py

state.py

vision/
├── camera.py
├── person_detection.py
├── person_tracking.py
└── gesture_recognition.py

target/
├── target_manager.py
└── proximity_manager.py

sensors/
└── distance_sensor.py

control/
├── center_controller.py
├── distance_controller.py
├── follow_controller.py
└── differential_drive.py

communication/
└── esp32_uart.py

ui/
├── hmi_manager.py
├── live_camera.py
├── robot_face.py
└── speech_manager.py

utils/
└── logger.py
```

Total:

**19 functional Python files**

---

# 28. File Responsibility Summary

| File                     | Main Responsibility                |
| ------------------------ | ---------------------------------- |
| `main.py`                | Main NEXUS orchestration loop      |
| `config.py`              | Global configuration               |
| `state.py`               | Robot state definitions            |
| `camera.py`              | Camera interface                   |
| `person_detection.py`    | Person detection                   |
| `person_tracking.py`     | Persistent person IDs              |
| `gesture_recognition.py` | Password gesture recognition       |
| `target_manager.py`      | Target lock and authentication     |
| `proximity_manager.py`   | Nearby-person greeting trigger     |
| `distance_sensor.py`     | Person/target distance             |
| `center_controller.py`   | Target horizontal centering        |
| `distance_controller.py` | Following-distance control         |
| `follow_controller.py`   | Generate \(V,\omega\)              |
| `differential_drive.py`  | Generate left/right wheel velocity |
| `esp32_uart.py`          | Raspberry Pi ↔ ESP32 communication |
| `hmi_manager.py`         | Monitor-state coordination         |
| `live_camera.py`         | Live camera monitor mode           |
| `robot_face.py`          | NEXUS face and animation           |
| `speech_manager.py`      | Voice output and speech events     |
| `logger.py`              | Debug and runtime logs             |

---

# 29. Final Software Architecture

The Raspberry Pi architecture is:

```text
PERCEPTION
    │
    ├── Camera
    ├── Person Detection
    ├── Person Tracking
    └── Gesture Recognition
              │
              ▼
         INTERACTION
              │
    ┌─────────┴─────────┐
    ▼                   ▼
Proximity          Authentication
Greeting               │
                       ▼
                  Target Manager
                       │
                       ▼
                    CONTROL
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
        Center Control      Distance Control
             │                   │
             └─────────┬─────────┘
                       ▼
                Follow Controller
                       │
                       ▼
                     V, ω
                       │
                       ▼
              Differential Drive
                       │
                       ▼
               V_left / V_right
                       │
                       ▼
                 COMMUNICATION
                       │
                       ▼
                     UART
                       │
                       ▼
                     ESP32
                       │
                       ▼
                 MOTOR CONTROL
```

The interaction architecture is:

```text
Robot State / Events
        │
        ▼
     HMI Manager
        │
   ┌────┴─────┐
   ▼          ▼
Monitor     Speech
```

---

# 30. Final Recommendation

The complete NEXUS software should be designed as a modular system rather than one large Python program.

The recommended implementation target is approximately:

```text
19 functional Python files
```

However, development should begin with approximately:

```text
9 Python files
```

for the initial person-following prototype.

The recommended development strategy is:

```text
Person Detection
      ↓
Person Tracking
      ↓
Basic Following
      ↓
ESP32 Motor Control
      ↓
Gesture Authentication
      ↓
Target Lock
      ↓
Greeting
      ↓
Speech
      ↓
HMI
      ↓
Safety and Refinement
```

The central design principle is:

> **Each Python file should have one clear responsibility.**

This keeps NEXUS easier to develop, debug, test, and extend.
