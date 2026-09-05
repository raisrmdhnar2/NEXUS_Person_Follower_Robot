
# NEXUS Configuration Specification

## 1. Purpose

This document defines configurable parameters used by NEXUS.

Configuration values shall be centralized rather than hard-coded throughout the software.

The purpose is to allow calibration and tuning without modifying the system architecture or module logic.

---

# 2. Configuration Categories

NEXUS configuration is divided into:

```text
Camera
Vision
Gesture
Greeting
Target Tracking
Following
Robot Geometry
Communication
Motor Control
Speech
HMI
Logging
```

---

# 3. Camera Configuration

```text
CAMERA_WIDTH
CAMERA_HEIGHT
CAMERA_FPS
```

Example initial values:

| Parameter         | Initial Value | Unit  |
| ----------------- | ------------: | ----- |
| `CAMERA_WIDTH`  |          1280 | pixel |
| `CAMERA_HEIGHT` |           720 | pixel |
| `CAMERA_FPS`    |            30 | FPS   |

These values may be changed according to Raspberry Pi 5 performance.

---

# 4. Person Detection Configuration

```text
PERSON_DETECTION_CONFIDENCE
PERSON_DETECTION_INTERVAL
```

| Parameter                       | Initial Value | Unit |
| ------------------------------- | ------------: | ---- |
| `PERSON_DETECTION_CONFIDENCE` |          0.50 | —   |
| `PERSON_DETECTION_INTERVAL`   |            10 | FPS  |

The detection threshold should be calibrated experimentally.

Higher confidence reduces false detections but may reduce detection recall.

---

# 5. Person Tracking Configuration

```text
TRACKER_MAX_LOST_FRAMES
TRACKER_MATCH_THRESHOLD
```

These values depend on the selected tracking algorithm.

The configuration should remain algorithm-independent where practical.

The tracking system should maintain IDs through short periods of detection loss.

---

# 6. Gesture Password Configuration

The NEXUS password is:

```text
🖐🏻
OPEN PALM
```

Configuration:

```text
GESTURE_CONFIDENCE_THRESHOLD
GESTURE_CONFIRMATION_FRAMES
GESTURE_COOLDOWN
```

Example initial values:

| Parameter                        | Initial Value |
| -------------------------------- | ------------: |
| `GESTURE_CONFIDENCE_THRESHOLD` |          0.80 |
| `GESTURE_CONFIRMATION_FRAMES`  |             3 |
| `GESTURE_COOLDOWN`             |         1.5 s |

The gesture should be confirmed across multiple frames.

A single-frame detection should not immediately trigger authentication.

---

# 7. Greeting Configuration

```text
GREETING_DISTANCE
GREETING_COOLDOWN
GREETING_REARM_DISTANCE
```

Example initial values:

| Parameter                   | Initial Value | Unit |
| --------------------------- | ------------: | ---- |
| `GREETING_DISTANCE`       |           2.0 | m    |
| `GREETING_COOLDOWN`       |           5.0 | s    |
| `GREETING_REARM_DISTANCE` |           2.5 | m    |

The exact values must be calibrated experimentally.

Greeting behavior:

```text
Person enters greeting range
        ↓
Greeting
        ↓
Cooldown / interaction lock
        ↓
Person leaves range
        ↓
Greeting re-armed
```

The greeting must not repeat continuously while the same person remains nearby.

---

# 8. Target Configuration

```text
TARGET_LOST_TIMEOUT
TARGET_REACQUISITION_WINDOW
```

Initial target-loss timeout:

```text
TARGET_LOST_TIMEOUT = 1–2 seconds
```

The target may temporarily disappear without immediately deactivating the robot.

If the target remains lost beyond the timeout:

```text
STOP
CLEAR TARGET
OFF
```

Automatic target replacement is disabled.

---

# 9. Follow Distance Configuration

```text
FOLLOW_DISTANCE
FOLLOW_DISTANCE_TOLERANCE
```

Example initial values:

| Parameter                     | Initial Value | Unit |
| ----------------------------- | ------------: | ---- |
| `FOLLOW_DISTANCE`           |           1.5 | m    |
| `FOLLOW_DISTANCE_TOLERANCE` |           0.2 | m    |

These values must be calibrated based on:

* Robot size
* Camera position
* Sensor position
* Motor response
* Environment

---

# 10. Follow Control Configuration

## Center Controller

```text
CENTER_KP
MAX_ANGULAR_VELOCITY
```

Example:

```text
CENTER_KP = configurable
MAX_ANGULAR_VELOCITY = configurable
```

The angular velocity must be saturated.

---

## Distance Controller

```text
DISTANCE_KP
MAX_LINEAR_VELOCITY
MIN_FOLLOW_DISTANCE
```

Initial behavior:

```text
Too far
    → move forward

Within tolerance
    → stop / slow

Too close
    → stop
```

Reverse movement is initially disabled.

---

# 11. Robot Geometry

The differential-drive controller requires physical robot dimensions.

```text
WHEEL_BASE
WHEEL_RADIUS
```

Where:

```text
WHEEL_BASE
    = distance between left and right drive-wheel centers

WHEEL_RADIUS
    = radius of each drive wheel
```

These values must be measured from the actual robot.

The differential-drive equations are:

$$
V_L=V-\frac{\omega W}{2}
$$

$$
V_R=V+\frac{\omega W}{2}
$$

---

# 12. Wheel Velocity Limits

```text
MAX_LEFT_WHEEL_VELOCITY
MAX_RIGHT_WHEEL_VELOCITY
```

Wheel commands must be limited before being transmitted to the ESP32.

Conceptually:

```text
Calculated Velocity
       ↓
Velocity Limiter
       ↓
Safe Wheel Velocity
       ↓
UART
```

---

# 13. UART Configuration

```text
UART_PORT
UART_BAUDRATE
UART_TIMEOUT
UART_COMMAND_RATE
```

Example:

| Parameter             | Initial Value |
| --------------------- | ------------- |
| `UART_BAUDRATE`     | 115200        |
| `UART_TIMEOUT`      | 0.2 s         |
| `UART_COMMAND_RATE` | 30 Hz         |

The actual serial device path depends on the Raspberry Pi hardware configuration.

---

# 14. ESP32 Communication Watchdog

The ESP32 must independently monitor command reception.

```text
ESP32_COMMAND_TIMEOUT
```

Example initial value:

```text
ESP32_COMMAND_TIMEOUT = 0.2 s
```

Behavior:

```text
Valid command received
      ↓
Reset watchdog
```

If no valid command arrives before timeout:

```text
Watchdog Timeout
      ↓
STOP LEFT MOTOR
STOP RIGHT MOTOR
```

This is a mandatory safety mechanism.

---

# 15. Encoder Configuration

```text
ENCODER_TICKS_PER_REV
ENCODER_SAMPLE_PERIOD
```

These values depend on the selected motor and encoder.

The encoder subsystem calculates:

```text
Pulse Count
    ↓
Wheel Rotation
    ↓
Wheel Speed
```

The actual encoder specification must be measured from the hardware.

---

# 16. PID Configuration

Each drive wheel has an independent PID controller.

```text
LEFT_KP
LEFT_KI
LEFT_KD

RIGHT_KP
RIGHT_KI
RIGHT_KD
```

Example structure:

```text
Left Motor:
    Kp
    Ki
    Kd

Right Motor:
    Kp
    Ki
    Kd
```

The gains must be experimentally tuned.

They should not be assumed to be identical if the physical motors behave differently.

---

# 17. PWM Configuration

ESP32 configuration:

```text
PWM_FREQUENCY
PWM_MIN
PWM_MAX
```

These values depend on:

* Motor driver
* Motor characteristics
* ESP32 PWM implementation

---

# 18. Speech Configuration

```text
SPEECH_ENABLED
SPEECH_COOLDOWN
FOLLOW_SPEECH_INTERVAL
```

The following speech should have cooldown control:

```text
"I’m right behind you."
```

Target-loss speech should occur once per loss event:

```text
"Where are you?"
```

Speech must not block the control loop.

---

# 19. HMI Configuration

```text
DISPLAY_WIDTH
DISPLAY_HEIGHT
HMI_FPS
SHOW_DEBUG_OVERLAY
```

Optional debug information:

```text
FPS
Person IDs
Target ID
Target distance
Target position
Robot state
Wheel velocity
UART status
```

Debug overlays should be disableable for demonstrations.

---

# 20. Logging Configuration

```text
LOG_LEVEL
LOG_TO_FILE
LOG_DIRECTORY
```

Recommended levels:

```text
DEBUG
INFO
WARNING
ERROR
CRITICAL
```

During development:

```text
LOG_LEVEL = DEBUG
```

During normal operation:

```text
LOG_LEVEL = INFO
```

---

# 21. Safety Configuration

Safety parameters should be centralized.

```text
MAX_LINEAR_VELOCITY
MAX_ANGULAR_VELOCITY
MIN_FOLLOW_DISTANCE
TARGET_LOST_TIMEOUT
ESP32_COMMAND_TIMEOUT
```

These parameters should have conservative initial values.

---

# 22. Configuration Ownership

Configuration is divided between Raspberry Pi and ESP32.

## Raspberry Pi

```text
Camera
Vision
Gesture
Greeting
Target
Follow Control
Robot Geometry
UART
HMI
Speech
Logging
```

## ESP32

```text
Motor pins
Encoder pins
PWM
PID
Motor limits
UART
Watchdog
```

---

# 23. Example Configuration Structure

The Python configuration may be organized conceptually as:

```text
Config
│
├── CameraConfig
├── VisionConfig
├── GestureConfig
├── GreetingConfig
├── TargetConfig
├── FollowConfig
├── RobotConfig
├── UARTConfig
├── HMIConfig
├── SpeechConfig
└── LoggingConfig
```

The ESP32 may use:

```text
Config
│
├── UARTConfig
├── MotorConfig
├── EncoderConfig
├── PIDConfig
└── SafetyConfig
```

---

# 24. Parameter Classification

Configuration values should be classified into three groups.

## Fixed

Values that normally should not change during operation.

Examples:

```text
Camera resolution
UART port
Motor pin assignment
Encoder pin assignment
```

## Calibration

Values adjusted during testing.

Examples:

```text
Detection threshold
Gesture threshold
FOLLOW_DISTANCE
CENTER_KP
DISTANCE_KP
PID gains
```

## Runtime

Values that may be changed while the system is running.

Examples:

```text
Robot state
Target ID
Current velocity
Current distance
```

Runtime values are not configuration constants and should not be stored as static configuration.

---

# 25. Recommended Initial Configuration

A starting configuration may be:

```text
Camera:
    1280 × 720
    30 FPS

Person Detection:
    confidence = 0.50
    10–20 FPS

Gesture:
    confidence = 0.80
    confirmation = 3 frames

Greeting:
    distance = 2.0 m

Following:
    target distance = 1.5 m
    lost timeout = 1–2 s

UART:
    115200 baud
    30 Hz command rate

ESP32:
    watchdog = 0.2 s

Reverse:
    disabled initially
```

These values are **initial engineering values**, not final calibrated values.

---

# 26. Configuration Safety Rules

1. Velocity limits must always be enforced.
2. Target-loss timeout must never be disabled during normal operation.
3. ESP32 communication watchdog must remain enabled.
4. Invalid configuration values should be rejected during initialization.
5. Configuration should be loaded before starting the control loop.
6. Hardware configuration must match the physical robot.
7. PID gains must be validated before autonomous following.
8. Safety limits must not be overridden by normal runtime commands.

---

# 27. Configuration Summary

The configuration system exists to separate:

```text
CODE
```

from:

```text
TUNABLE PARAMETERS
```

The intended relationship is:

```text
config.py
     │
     ├── Vision Parameters
     ├── Gesture Parameters
     ├── Greeting Parameters
     ├── Follow Parameters
     ├── Robot Geometry
     ├── Communication
     └── HMI/Speech
          │
          ▼
      NEXUS Modules
```

The ESP32 uses its own configuration for:

```text
UART
Motor
Encoder
PID
PWM
Safety Watchdog
```

The final values must be established through hardware calibration and system testing.
