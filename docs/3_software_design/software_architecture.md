
# NEXUS Software Architecture

## 1. Purpose

This document defines the software architecture of the NEXUS robot.

It translates the system architecture and subsystem design into a software structure that can be implemented on the Raspberry Pi 5 and ESP32.

The architecture follows a modular design so that perception, target management, control, communication, HMI, and motor control can be developed and tested independently.

---

# 2. Software Platform

## Raspberry Pi 5

The Raspberry Pi runs the high-level NEXUS software.

Primary responsibilities:

* Camera processing
* Person detection
* Person tracking
* Gesture recognition
* Authentication
* Target management
* State machine
* Follow control
* HMI
* Speech
* UART communication

Expected environment:

```text
OS:
    Linux

Language:
    Python 3

Main libraries/frameworks:
    OpenCV
    YOLO-compatible detection framework
    ByteTrack / BoT-SORT
    MediaPipe or equivalent hand-tracking framework
    PySerial
```

The exact library versions are implementation decisions and should be recorded separately.

---

## ESP32

The ESP32 runs the low-level motor-control firmware.

Primary responsibilities:

* UART command reception
* Encoder reading
* Wheel-speed calculation
* PID control
* PWM generation
* Motor driver control
* Communication watchdog
* Motor safety

Recommended language:

```text
C/C++
```

---

# 3. Software Layer Architecture

The Raspberry Pi software is divided into five logical layers.

```text
┌─────────────────────────────────────────┐
│              APPLICATION                │
│                  main.py                │
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│             ROBOT LOGIC                 │
│ State Machine                           │
│ Target Manager                          │
│ Authentication                          │
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│              PERCEPTION                 │
│ Camera                                  │
│ Person Detection                        │
│ Person Tracking                         │
│ Gesture Recognition                     │
│ Proximity                               │
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│               CONTROL                   │
│ Center Controller                       │
│ Distance Controller                     │
│ Follow Controller                       │
│ Differential Drive                      │
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│          HARDWARE INTERFACE             │
│ UART                                    │
│ Distance Sensor                         │
└─────────────────────────────────────────┘
```

The HMI and speech system operate alongside the main robot logic.

---

# 4. Raspberry Pi Software Structure

```text
raspberry_pi/
│
├── main.py
├── config.py
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

---

# 5. Application Layer

## `main.py`

`main.py` is the application entry point and system coordinator.

It is responsible for:

* Initializing subsystems
* Running the main application loop
* Collecting subsystem outputs
* Sending events to the state machine
* Calling appropriate high-level actions
* Coordinating shutdown

`main.py` should **not** contain detailed implementation of detection, tracking, control, or motor algorithms.

The architecture should avoid turning `main.py` into a large monolithic program.

---

# 6. Configuration Layer

## `config.py`

Contains configurable parameters.

Examples:

```text
Camera:
    width
    height
    FPS

Vision:
    detection confidence
    gesture confidence

Greeting:
    greeting distance
    greeting cooldown

Following:
    target distance
    target lost timeout
    maximum linear velocity
    maximum angular velocity

Robot:
    wheel base
    wheel radius

Communication:
    UART port
    baud rate
    command timeout
```

Configuration values should not be scattered throughout the code.

---

# 7. State Layer

## `state.py`

Contains the robot state representation and state-transition logic.

States:

```text
OFF
GREETING
TARGET_LOCK
FOLLOW
DEACTIVATING
ERROR
```

The state machine should process events rather than allowing arbitrary modules to directly change the global state.

---

# 8. Perception Layer

The perception layer converts raw camera frames into structured information.

```text
Camera
  ↓
Person Detection
  ↓
Person Tracking
  ↓
Tracked Persons
```

In parallel:

```text
Camera
  ↓
Gesture Recognition
  ↓
Gesture
```

---

# 9. Target Layer

The target layer connects perception with robot behavior.

```text
Tracked Persons
      +
Gesture
      ↓
Gesture-Person Association
      ↓
Authentication
      ↓
Target Manager
```

The Target Manager is the only module responsible for maintaining the active `target_id`.

---

# 10. Control Layer

The control layer converts target information into wheel commands.

```text
Target Position
      ↓
Center Controller
      ↓
ω

Target Distance
      ↓
Distance Controller
      ↓
V

V + ω
 ↓
Follow Controller
 ↓
Differential Drive
 ↓
V_left, V_right
```

---

# 11. Communication Layer

The Raspberry Pi communicates with the ESP32 through UART.

```text
Differential Drive
      ↓
ESP32 UART
      ↓
ESP32 Firmware
```

The communication module must isolate the rest of the Python software from the low-level serial implementation.

---

# 12. HMI Layer

The HMI layer displays the current robot state.

```text
Robot State
     ↓
HMI Manager
     │
     ├── Live Camera
     ├── Robot Face
     └── Animation
```

The HMI must not independently modify the robot state.

---

# 13. Speech Layer

Speech is event-driven.

```text
Robot Event
     ↓
Speech Manager
     ↓
Audio Output
```

Speech should execute asynchronously so that it does not block perception or control.

---

# 14. ESP32 Software Architecture

The ESP32 firmware is structured as:

```text
esp32/
│
├── platformio.ini
│
└── src/
    ├── main.cpp
    ├── uart_command.cpp
    ├── uart_command.h
    ├── motor_control.cpp
    ├── motor_control.h
    ├── encoder.cpp
    ├── encoder.h
    ├── pid.cpp
    ├── pid.h
    └── config.h
```

---

# 15. ESP32 Execution Flow

```text
UART Command
      ↓
Command Parser
      ↓
Wheel Setpoints
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

The ESP32 control loop must be independent from Raspberry Pi vision processing.

---

# 16. Inter-Module Communication

Modules communicate through structured data.

Conceptual data types include:

```text
Frame
PersonDetection
TrackedPerson
GestureDetection
AuthenticationResult
Target
RobotState
FollowCommand
WheelCommand
ESP32Status
```

Modules should not directly modify another module's internal variables.

---

# 17. Main Software Data Flow

```text
Camera
  │
  ├────────► Person Detection
  │               │
  │               ▼
  │        Person Tracking
  │               │
  │               ▼
  │        Target Manager
  │
  └────────► Gesture Recognition
                  │
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
                  │
                  ▼
          Differential Drive
                  │
                  ▼
              UART
                  │
                  ▼
                ESP32
```

---

# 18. Concurrency Model

NEXUS should not process every subsystem sequentially at the same frequency.

Conceptually:

```text
Camera Thread / Process
        ↓
Vision Processing

Tracking Loop
        ↓
Target Update

Control Loop
        ↓
Velocity Command

UART Loop
        ↓
ESP32 Communication

HMI Loop
        ↓
Display

Speech Worker
        ↓
Audio
```

The exact threading/process architecture should be selected during implementation based on Raspberry Pi 5 performance measurements.

The critical principle is that slow operations such as speech playback must not block motor control.

---

# 19. Error Handling Architecture

Errors should propagate through structured status/events.

Example:

```text
Camera Failure
     ↓
Camera Module
     ↓
System Error Event
     ↓
State Machine
     ↓
ERROR
     ↓
Motor STOP
```

For communication:

```text
UART Failure
     ↓
ESP32 Watchdog
     ↓
Motor STOP
```

---

# 20. Software Safety Rules

### Rule 1

No module other than the State Machine may arbitrarily change robot state.

### Rule 2

Only Target Manager owns `target_id`.

### Rule 3

Only the Control layer generates wheel commands.

### Rule 4

Only the Communication layer sends wheel commands to the ESP32.

### Rule 5

Speech must never block control.

### Rule 6

HMI must never block safety-critical control.

### Rule 7

ESP32 must independently stop motors after communication timeout.

### Rule 8

No target may be automatically replaced after target-loss timeout.

---

# 21. Architecture Dependency Direction

The preferred dependency direction is:

```text
Application
    ↓
Robot Logic
    ↓
Subsystems
    ↓
Hardware Interfaces
```

Avoid circular dependencies.

For example:

```text
person_tracking.py
```

should not import:

```text
follow_controller.py
```

just to control the robot.

Instead:

```text
Person Tracking
      ↓
Tracked Data
      ↓
Target Manager
      ↓
Follow Controller
```

---

# 22. Software Architecture Summary

The complete software architecture is:

```text
                  NEXUS APPLICATION
                         │
                      main.py
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   Robot Logic       Perception          HMI
        │                │                │
        ▼                ▼                ▼
 State Machine      Camera/Vision     Display/Speech
        │
        ▼
 Target Management
        │
        ▼
 Follow Control
        │
        ▼
 Differential Drive
        │
        ▼
 Communication
        │
        ▼
       ESP32
        │
        ▼
 Motor Control
```

This architecture provides a clear separation between **perception, decision-making, control, user interaction, communication, and actuation**.
