
# NEXUS Module Specification

## 1. Purpose

This document specifies the software modules required to implement NEXUS.

For each module, this document defines:

* Responsibility
* Input
* Output
* Main operations
* Dependencies
* Implementation boundary

The purpose is to provide a direct reference for implementation.

---

# 2. Raspberry Pi Modules

## 2.1 `main.py`

### Responsibility

System-level application coordinator.

### Input

Outputs from all major subsystems.

### Output

System actions and events.

### Main operations

```text
initialize_system()
run()
shutdown()
```

### Dependencies

All high-level subsystems.

### Boundary

`main.py` coordinates modules but should not implement their internal algorithms.

---

# 3. `config.py`

### Responsibility

Central configuration repository.

### Contains

```text
Camera configuration
Detection thresholds
Gesture thresholds
Greeting distance
Greeting cooldown
Follow distance
Target lost timeout
Velocity limits
Robot geometry
UART configuration
```

### Output

Configuration values accessible to other modules.

---

# 4. `state.py`

### Responsibility

Implement the NEXUS state machine.

### States

```text
OFF
GREETING
TARGET_LOCK
FOLLOW
DEACTIVATING
ERROR
```

### Inputs

```text
Robot Events
```

Examples:

```text
PERSON_NEARBY
GREETING_COMPLETE
PASSWORD_ACCEPTED
TARGET_LOCKED
TARGET_LOST
TARGET_REACQUIRED
TARGET_LOST_TIMEOUT
TARGET_DEACTIVATION
SYSTEM_ERROR
```

### Output

```text
Current Robot State
State Transition Events
```

### Main operations

```text
handle_event()
transition()
get_state()
```

---

# 5. `vision/camera.py`

### Responsibility

Manage camera hardware and image capture.

### Input

Camera hardware.

### Output

```text
Image Frame
```

### Main operations

```text
initialize()
read()
release()
```

### Boundary

Does not perform detection or tracking.

---

# 6. `vision/person_detection.py`

### Responsibility

Detect people in camera frames.

### Input

```text
Image Frame
```

### Output

```text
PersonDetection[]
```

### Main operations

```text
detect(frame)
```

### PersonDetection

Conceptually:

```text
PersonDetection
├── bbox
├── confidence
└── class_id
```

### Dependencies

* Camera frame
* Detection model

---

# 7. `vision/person_tracking.py`

### Responsibility

Maintain persistent person identities.

### Input

```text
PersonDetection[]
```

### Output

```text
TrackedPerson[]
```

### Main operations

```text
update(detections)
get_tracks()
get_track(track_id)
```

### TrackedPerson

```text
TrackedPerson
├── track_id
├── bbox
├── center
├── confidence
└── status
```

### Dependencies

Person Detection.

---

# 8. `vision/gesture_recognition.py`

### Responsibility

Recognize the NEXUS password gesture.

The password is:

```text
🖐🏻
OPEN PALM
```

### Input

```text
Image Frame
```

### Output

```text
GestureDetection
```

### Main operations

```text
detect(frame)
classify(hand_landmarks)
```

### GestureDetection

```text
GestureDetection
├── gesture_type
├── confidence
├── hand_bbox
└── hand_center
```

### Valid gesture

```text
gesture_type = PASSWORD
```

### Dependencies

* Camera
* Hand/landmark detection system

---

# 9. Gesture-Person Association

The association logic may initially be implemented inside the authentication/target layer rather than as a separate Python file.

### Responsibility

Determine which tracked person performed a detected gesture.

### Input

```text
TrackedPerson[]
+
GestureDetection
```

### Output

```text
gesture_person_id
```

### Main operation

```text
associate_gesture_with_person()
```

### Association principle

Use spatial relationships between the detected hand and tracked person's bounding box.

---

# 10. `target/proximity_manager.py`

### Responsibility

Determine whether a person is within greeting range.

### Input

```text
TrackedPerson[]
+
Distance Measurement
```

### Output

```text
PERSON_NEARBY event
```

### Main operations

```text
update()
is_person_nearby()
should_greet()
reset_greeting()
```

### Responsibilities

* Greeting range detection
* Greeting cooldown
* Interaction tracking
* Greeting reset when person leaves range

---

# 11. `target/target_manager.py`

### Responsibility

Manage the authenticated target.

### Input

```text
TrackedPerson[]
AuthenticationResult
Distance
```

### Output

```text
Target
Target Events
```

### Main operations

```text
lock_target(track_id)
get_target()
update_target(tracks)
is_target_visible()
clear_target()
```

### Target

```text
Target
├── track_id
├── bbox
├── center
├── distance
├── visible
└── status
```

### Critical rule

This module is the **only owner of `target_id`**.

---

# 12. `sensors/distance_sensor.py`

### Responsibility

Read and process the distance sensor.

### Input

Distance sensor hardware.

### Output

```text
distance
```

### Main operations

```text
initialize()
read_distance()
is_valid()
```

### Units

The internal system should use a consistent unit, preferably meters.

---

# 13. `control/center_controller.py`

### Responsibility

Generate angular velocity from target horizontal position.

### Input

```text
Target center X
Image width
```

### Processing

$$
x_{camera}=\frac{W}{2}
$$

$$
e_x=x_c-x_{camera}
$$

### Output

```text
ω
```

### Main operation

```text
compute(target_center_x, image_width)
```

### Initial controller

A proportional controller may be used:

$$
\omega=K_xe_x
$$

with output saturation.

---

# 14. `control/distance_controller.py`

### Responsibility

Generate linear velocity from target distance.

### Input

```text
Measured distance
Desired distance
```

### Processing

$$
e_d=D_{person}-D_{target}
$$

### Output

```text
V
```

### Main operation

```text
compute(distance)
```

### Initial behavior

```text
Too far
    → Forward

Desired distance
    → Stop / slow

Too close
    → Stop
```

Reverse movement should initially be disabled.

---

# 15. `control/follow_controller.py`

### Responsibility

Combine target position and distance information into robot-level motion commands.

### Input

```text
Target position
Target distance
```

### Output

```text
FollowCommand
├── linear_velocity
└── angular_velocity
```

### Main operation

```text
compute(target)
```

### Dependencies

* Center Controller
* Distance Controller

---

# 16. `control/differential_drive.py`

### Responsibility

Convert robot velocity into individual wheel velocities.

### Input

```text
V
ω
Wheel Base W
```

### Output

```text
WheelCommand
├── left_velocity
└── right_velocity
```

### Equations

$$
V_L=V-\frac{\omega W}{2}
$$

$$
V_R=V+\frac{\omega W}{2}
$$

### Main operation

```text
compute_wheel_velocities(V, omega)
```

---

# 17. `communication/esp32_uart.py`

### Responsibility

Manage Raspberry Pi ↔ ESP32 communication.

### Input

```text
WheelCommand
```

### Output

```text
ESP32Status
```

### Main operations

```text
connect()
send_velocity()
send_stop()
read_status()
close()
```

### Responsibilities

* Open UART
* Format commands
* Transmit commands
* Receive responses
* Detect communication failure
* Handle serial errors

Detailed packet formatting belongs in `communication_protocol.md`.

---

# 18. `ui/hmi_manager.py`

### Responsibility

Coordinate visual interface according to robot state.

### Input

```text
Robot State
Camera Frame
Robot Events
```

### Output

Display updates.

### Main operations

```text
update()
set_state()
show_camera()
show_face()
show_animation()
```

---

# 19. `ui/live_camera.py`

### Responsibility

Display the live camera feed.

### Input

```text
Image Frame
```

### Output

Monitor display.

### Used primarily by

```text
OFF
```

---

# 20. `ui/robot_face.py`

### Responsibility

Render NEXUS's robot face and expressions.

### Input

```text
Robot State
Robot Event
```

### Output

Rendered face.

### Example expressions

```text
Normal     (•‿•)
Happy      (^‿^)
Lost       (•︵•)
Confused   (⊙_⊙)
Error      (×_×)
```

---

# 21. `ui/speech_manager.py`

### Responsibility

Manage NEXUS speech output.

### Input

```text
Speech Event
```

### Output

Audio.

### Speech mapping

```text
PERSON_NEARBY
    →
"Welcome to the Technology and Information Department of Brawijaya University! Hello! I’m NEXUS. I’m ready to follow you. Please show me the password."

ACTIVATED
    →
"Hello! Nice to see you."

TARGET_LOCKED
    →
"I’ll follow you."

FOLLOWING
    →
"I’m right behind you."

TARGET_LOST
    →
"Where are you?"

TARGET_LOST_TIMEOUT
    →
"I can’t find you."

DEACTIVATED
    →
"Okay! See you later!"

SYSTEM_ERROR
    →
"Something went wrong."
```

### Requirements

* Speech must not block control.
* Speech must use cooldowns where necessary.
* Repeated speech events must be filtered.

---

# 22. `utils/logger.py`

### Responsibility

Provide centralized logging.

### Inputs

```text
Log Event
```

### Outputs

```text
Console
Log File
```

### Log levels

```text
DEBUG
INFO
WARNING
ERROR
CRITICAL
```

### Important events

```text
System startup
Camera failure
Person detected
Gesture detected
Authentication success/failure
Target locked
Target lost
Target reacquired
Target timeout
State transition
UART failure
Motor command failure
System error
```

---

# 23. ESP32 Modules

## `main.cpp`

### Responsibility

Initialize and run the ESP32 firmware.

### Responsibilities

* Initialize UART
* Initialize encoders
* Initialize motor control
* Initialize PID
* Run control loop
* Monitor communication timeout

---

# 24. `uart_command.cpp`

### Responsibility

Receive and parse Raspberry Pi commands.

### Input

UART data.

### Output

```text
Left wheel setpoint
Right wheel setpoint
```

### Responsibilities

* Packet parsing
* Validation
* Command timeout
* Invalid command handling

---

# 25. `motor_control.cpp`

### Responsibility

Control motor-driver outputs.

### Input

```text
PWM command
Direction command
```

### Output

Motor-driver signals.

### Responsibilities

* Direction
* PWM
* Stop
* Motor enable/disable

---

# 26. `encoder.cpp`

### Responsibility

Read wheel encoders.

### Input

Encoder signals.

### Output

```text
Left wheel speed
Right wheel speed
```

### Responsibilities

* Pulse counting
* Direction detection
* Speed calculation

---

# 27. `pid.cpp`

### Responsibility

Implement independent PID controllers for the left and right wheels.

### Input

```text
Desired wheel speed
Measured wheel speed
```

### Output

```text
PWM command
```

### Conceptual flow

```text
Setpoint
   +
Measured Speed
   ↓
Error
   ↓
PID
   ↓
PWM
```

---

# 28. `config.h`

### Responsibility

Store ESP32 hardware and control configuration.

Examples:

```text
UART baud rate
Motor pins
Encoder pins
PWM frequency
PWM limits
PID gains
Communication timeout
```

---

# 29. Module Dependency Graph

```text
                       main.py
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
      state.py        perception          HMI
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
          Camera       Detection     Gesture
                          │
                          ▼
                       Tracking
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
       Target Manager           Authentication
             │                         │
             └────────────┬────────────┘
                          ▼
                   Follow Controller
                     ┌────┴────┐
                     ▼         ▼
                  Center    Distance
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
                   PID       Encoder
                    │           │
                    └─────┬─────┘
                          ▼
                        Motor
```

---

# 30. Core Data Structures

The implementation should define standardized structures for communication between modules.

## PersonDetection

```text
PersonDetection
├── bbox
├── confidence
└── class_id
```

## TrackedPerson

```text
TrackedPerson
├── track_id
├── bbox
├── center
├── confidence
└── status
```

## GestureDetection

```text
GestureDetection
├── gesture_type
├── confidence
├── hand_bbox
└── hand_center
```

## AuthenticationResult

```text
AuthenticationResult
├── valid
├── person_id
└── event
```

## Target

```text
Target
├── track_id
├── bbox
├── center
├── distance
├── visible
└── status
```

## FollowCommand

```text
FollowCommand
├── linear_velocity
└── angular_velocity
```

## WheelCommand

```text
WheelCommand
├── left_velocity
└── right_velocity
```

---

# 31. Module Responsibility Rules

### Person Detection

Answers:

> "Where are the people?"

### Person Tracking

Answers:

> "Which detected person is which?"

### Gesture Recognition

Answers:

> "Is the hand performing the password gesture?"

### Gesture-Person Association

Answers:

> "Which tracked person performed the gesture?"

### Authentication

Answers:

> "Should this gesture be accepted?"

### Target Manager

Answers:

> "Who is NEXUS following?"

### State Machine

Answers:

> "What should NEXUS do now?"

### Follow Controller

Answers:

> "How should NEXUS move toward the target?"

### Differential Drive

Answers:

> "What should each wheel velocity be?"

### ESP32 PID

Answers:

> "How should each motor achieve its commanded wheel velocity?"

---

# 32. Implementation Boundary

The following logic must remain separate:

```text
Detection
≠
Tracking
≠
Authentication
≠
Target Management
≠
State Management
≠
Motion Control
≠
Motor Control
```

The intended implementation pipeline is:

```text
Camera
 ↓
Detection
 ↓
Tracking
 ↓
Gesture / Association
 ↓
Authentication
 ↓
Target Manager
 ↓
State Machine
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

---

# 33. Final Module List

## Raspberry Pi

| File                       | Primary Responsibility     |
| -------------------------- | -------------------------- |
| `main.py`                | Application coordination   |
| `config.py`              | Configuration              |
| `state.py`               | State machine              |
| `camera.py`              | Camera                     |
| `person_detection.py`    | Person detection           |
| `person_tracking.py`     | Person tracking            |
| `gesture_recognition.py` | Password gesture           |
| `proximity_manager.py`   | Greeting proximity         |
| `target_manager.py`      | Target management          |
| `distance_sensor.py`     | Distance measurement       |
| `center_controller.py`   | Horizontal control         |
| `distance_controller.py` | Distance control           |
| `follow_controller.py`   | Follow control             |
| `differential_drive.py`  | Wheel velocity calculation |
| `esp32_uart.py`          | Pi ↔ ESP32 communication  |
| `hmi_manager.py`         | HMI coordination           |
| `live_camera.py`         | Camera display             |
| `robot_face.py`          | Robot face                 |
| `speech_manager.py`      | Speech                     |
| `logger.py`              | Logging                    |

## ESP32

| File                    | Primary Responsibility |
| ----------------------- | ---------------------- |
| `main.cpp`            | Firmware entry point   |
| `uart_command.cpp/h`  | UART command parsing   |
| `motor_control.cpp/h` | Motor driver control   |
| `encoder.cpp/h`       | Encoder processing     |
| `pid.cpp/h`           | Wheel PID              |
| `config.h`            | Firmware configuration |

---

# 34. Design Principle

The NEXUS software should follow one fundamental principle:

> **Each module should have one clear responsibility and communicate with other modules through well-defined data interfaces.**

The software architecture should make it possible to replace an individual component—for example, the person detector or tracking algorithm—without requiring major changes to unrelated modules.
