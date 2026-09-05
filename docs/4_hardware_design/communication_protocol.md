# NEXUS — Communication Protocol

## 1. Purpose

This document defines the communication protocol between the **Raspberry Pi 5** and **ESP32** in the NEXUS mobile human-following robot.

The protocol defines:

* Communication architecture.
* Physical interface.
* UART configuration.
* Message types.
* Message format.
* Command semantics.
* ESP32 status messages.
* Timing requirements.
* Watchdog behavior.
* Error handling.
* Safety requirements.
* Raspberry Pi and ESP32 responsibilities.

The Raspberry Pi is responsible for high-level robot intelligence, while the ESP32 is responsible for low-level motor execution.

---

# 2. Communication Architecture

The communication architecture is:

```text
                    NEXUS
                      │
              ┌───────┴───────┐
              │               │
        Raspberry Pi 5      ESP32
        High-Level          Low-Level
        Processing          Control
              │               │
              │     UART      │
              └───────────────┘
                      │
                Motor Driver
                      │
              ┌───────┴───────┐
              │               │
          Left Motor      Right Motor
```

The Raspberry Pi sends high-level motor velocity commands to the ESP32.

The ESP32:

1. Receives the command.
2. Validates the command.
3. Converts the requested wheel velocity into motor control.
4. Reads encoder feedback.
5. Runs PID control.
6. Drives the motor driver.
7. Reports status back to the Raspberry Pi.

---

# 3. Responsibility Boundary

## 3.1 Raspberry Pi

The Raspberry Pi is responsible for:

* Person detection.
* Person tracking.
* Gesture recognition.
* Gesture-person association.
* Authentication.
* Target selection.
* Target management.
* Robot state machine.
* Follow controller.
* Distance control.
* Centering control.
* Differential-drive calculation.
* Generation of left/right wheel velocity commands.
* Sending commands through UART.
* HMI.
* Speech.

The Raspberry Pi does **not** directly control motor PWM.

---

## 3.2 ESP32

The ESP32 is responsible for:

* UART reception.
* UART command validation.
* Wheel velocity command execution.
* Encoder acquisition.
* Wheel-speed estimation.
* PID control.
* PWM generation.
* Motor-driver control.
* Communication watchdog.
* Motor safety stop.

The ESP32 does **not** perform:

* Person detection.
* Person tracking.
* Gesture recognition.
* Authentication.
* Target selection.
* Follow decision making.
* Speech.
* HMI control.

---

# 4. Physical Interface

The initial communication interface is:

**UART / TTL Serial**

Recommended configuration:

| Parameter     | Value       |
| ------------- | ----------- |
| Interface     | UART        |
| Baud Rate     | 115200      |
| Data Bits     | 8           |
| Parity        | None        |
| Stop Bits     | 1           |
| Flow Control  | None        |
| Logic Level   | 3.3 V       |
| Communication | Full duplex |

Configuration:

```text
Raspberry Pi TX ─────────→ ESP32 RX
Raspberry Pi RX ←───────── ESP32 TX
Raspberry Pi GND ───────── ESP32 GND
```

The Raspberry Pi and ESP32 must share a common electrical reference.

> The exact GPIO pins shall be defined in `pinout.md`.

---

# 5. UART Configuration

The default UART configuration is:

```text
Baud Rate : 115200
Data       : 8 bits
Parity     : None
Stop       : 1 bit
Flow       : None
```

Therefore:

```text
115200 8N1
```

The protocol shall use ASCII text messages during the initial development phase because they are easy to inspect, debug, and log.

A binary protocol may be considered later if bandwidth or latency becomes a significant limitation.

---

# 6. Communication Direction

The protocol supports two communication directions.

### Raspberry Pi → ESP32

Used for:

* Motor velocity commands.
* Stop commands.
* Connection/health checks.

### ESP32 → Raspberry Pi

Used for:

* Motor status.
* Encoder information.
* Current wheel speed.
* Error status.
* Health response.

---

# 7. Message Types

## 7.1 Raspberry Pi → ESP32

| Message    | Purpose                                 |
| ---------- | --------------------------------------- |
| `VELOCITY` | Command wheel velocities                |
| `STOP`     | Immediately command both wheels to stop |
| `PING`     | Check communication                     |

---

## 7.2 ESP32 → Raspberry Pi

| Message  | Purpose                            |
| -------- | ---------------------------------- |
| `STATUS` | Report motor and encoder status    |
| `PONG`   | Response to `PING`                 |
| `ERROR`  | Report communication/control error |

---

# 8. Message Format

The initial protocol uses a line-based ASCII format.

Each message:

```text
<COMMAND>,<FIELD1>,<FIELD2>,...<FIELDN>\n
```

Example:

```text
VELOCITY,0.40,0.40\n
```

The newline character marks the end of the packet.

---

# 9. VELOCITY Command

## 9.1 Purpose

`VELOCITY` commands the desired left and right wheel velocities.

Format:

```text
VELOCITY,<left_velocity>,<right_velocity>\n
```

Example:

```text
VELOCITY,0.40,0.40
```

where:

```text
left_velocity  = 0.40
right_velocity = 0.40
```

The exact unit shall be standardized to:

**meters per second (m/s)**

---

# 10. Wheel Velocity Convention

Positive velocity:

```text
Positive → Forward
```

Negative velocity:

```text
Negative → Reverse
```

Zero:

```text
0.0 → Stop
```

Example:

```text
VELOCITY,0.50,0.50
```

means:

```text
Left wheel  → forward at 0.50 m/s
Right wheel → forward at 0.50 m/s
```

---

# 11. Differential Drive Example

The Raspberry Pi calculates:

$$
V_L=V-\frac{\omega W}{2}
$$

$$
V_R=V+\frac{\omega W}{2}
$$

The resulting values are transmitted to the ESP32.

Example:

```text
VELOCITY,0.30,0.50
```

This indicates:

```text
Left wheel  = 0.30 m/s
Right wheel = 0.50 m/s
```

The robot therefore performs a turning maneuver.

The ESP32 does not need to know the robot's desired \(V\) and \(\omega\). It only needs to execute the wheel velocity commands.

---

# 12. STOP Command

## 12.1 Purpose

`STOP` commands an immediate motor stop.

Format:

```text
STOP\n
```

Example:

```text
STOP
```

Upon receiving a valid `STOP` command, the ESP32 shall:

1. Set left wheel target velocity to zero.
2. Set right wheel target velocity to zero.
3. Update the PID target.
4. Stop PWM when appropriate.
5. Ensure both motors are not commanded to move.

---

# 13. STOP Priority

`STOP` shall have higher execution priority than `VELOCITY`.

If the ESP32 receives:

```text
VELOCITY,0.5,0.5
STOP
```

the final motor command shall be:

```text
LEFT  = 0
RIGHT = 0
```

A STOP condition must not be overridden by a previously received velocity command.

---

# 14. PING Command

## 14.1 Purpose

`PING` verifies that the Raspberry Pi and ESP32 communication link is functioning.

Raspberry Pi:

```text
PING
```

ESP32:

```text
PONG
```

Example:

```text
Pi → ESP32
PING\n

ESP32 → Pi
PONG\n
```

The response may be used for:

* Connection testing.
* Startup verification.
* Debugging.
* Communication diagnostics.

---

# 15. STATUS Message

The ESP32 periodically reports its operating status.

Format:

```text
STATUS,<left_speed>,<right_speed>,<left_encoder>,<right_encoder>,<error>\n
```

Example:

```text
STATUS,0.38,0.41,12450,12510,0
```

Fields:

| Field           | Description                |
| --------------- | -------------------------- |
| `STATUS`        | Message identifier         |
| `left_speed`    | Measured left wheel speed  |
| `right_speed`   | Measured right wheel speed |
| `left_encoder`  | Left encoder count         |
| `right_encoder` | Right encoder count        |
| `error`         | Error code                 |

---

# 16. Encoder Convention

Encoder counts shall use signed or otherwise consistently interpreted counts.

Recommended convention:

```text
Forward → increasing count
Reverse → decreasing count
```

The exact implementation depends on the encoder hardware and motor orientation.

The convention must be verified during hardware testing.

---

# 17. Speed Measurement

The ESP32 calculates wheel speed from encoder feedback.

Conceptually:

$$
v=\frac{\Delta N}{N_{rev}}
\frac{2\pi R}{\Delta t}
$$

where:

* \(v\) = wheel linear velocity.
* \(\Delta N\) = encoder count change.
* \(N_{rev}\) = encoder counts per wheel revolution.
* \(R\) = wheel radius.
* \(\Delta t\) = measurement interval.

The measured wheel speed is used as feedback for the PID controller.

---

# 18. PID Control

The ESP32 controls each wheel independently.

```text
Left Command
     ↓
Left PID
     ↓
Left PWM
     ↓
Left Motor

Right Command
     ↓
Right PID
     ↓
Right PWM
     ↓
Right Motor
```

For each wheel:

$$
e(t)=v_{target}(t)-v_{actual}(t)
$$

The PID controller attempts to minimize this error.

---

# 19. Communication Watchdog

The ESP32 shall implement an independent communication watchdog.

Initial timeout:

$$
T_{watchdog}=0.2\,s
$$

The watchdog timer is reset whenever a valid motor-control message is received.

A valid `VELOCITY` or `STOP` command shall reset the watchdog.

---

# 20. Watchdog Timeout Behavior

If no valid command is received for longer than:

$$
T_{watchdog}
$$

the ESP32 shall automatically stop both motors.

Behavior:

```text
No valid UART command
        ↓
0.2 s timeout
        ↓
Watchdog triggered
        ↓
Left velocity = 0
Right velocity = 0
        ↓
Motors STOP
```

This protection is independent of Raspberry Pi software.

---

# 21. Watchdog Safety Principle

The Raspberry Pi shall **not** be the only layer responsible for stopping the robot.

The safety architecture is:

```text
             Raspberry Pi
                  │
          Target-loss logic
                  │
               STOP
                  │
                 UART
                  │
                ESP32
                  │
          Communication Watchdog
                  │
                 STOP
                  │
              Motor Driver
```

Therefore:

* Raspberry Pi can command STOP.
* ESP32 can independently stop the motors.
* UART communication failure cannot leave the motors running indefinitely.

---

# 22. Command Rate

The Raspberry Pi shall transmit velocity commands at approximately:

$$
f_{command}=30\,Hz
$$

Therefore:

$$
T_{command}\approx33\,ms
$$

This provides sufficient margin relative to the initial:

$$
T_{watchdog}=200\,ms
$$

Example:

```text
t = 0 ms     VELOCITY
t = 33 ms    VELOCITY
t = 66 ms    VELOCITY
t = 99 ms    VELOCITY
t = 132 ms   VELOCITY
t = 165 ms   VELOCITY
...
```

A communication delay greater than the watchdog timeout causes a safe stop.

---

# 23. Raspberry Pi Command Generation

The Raspberry Pi should follow this pipeline:

```text
Target
  ↓
Center Controller
  ↓
Distance Controller
  ↓
Follow Controller
  ↓
V, ω
  ↓
Differential Drive
  ↓
VL, VR
  ↓
Velocity Limiter
  ↓
UART
  ↓
ESP32
```

The ESP32 receives only the final wheel velocity commands.

---

# 24. Velocity Limiting

Before transmission, the Raspberry Pi shall apply software limits:

```text
|VL| ≤ MAX_LEFT_WHEEL_VELOCITY
|VR| ≤ MAX_RIGHT_WHEEL_VELOCITY
```

The ESP32 shall also enforce its own hardware/firmware limits.

Therefore:

```text
Raspberry Pi limit
        +
ESP32 limit
        ↓
Defense in depth
```

The ESP32 must never blindly execute an out-of-range velocity command.

---

# 25. Invalid Command Handling

The ESP32 shall reject malformed messages.

Examples:

```text
VELOCITY
VELOCITY,abc,0.4
VELOCITY,0.4
VELOCITY,0.4,0.4,123
UNKNOWN,0.4,0.4
```

Expected behavior:

```text
Invalid packet
     ↓
Reject
     ↓
Do not execute new velocity
```

If communication remains invalid until the watchdog expires:

```text
Watchdog timeout
     ↓
STOP
```

---

# 26. Numeric Validation

The ESP32 shall validate numerical values before execution.

For example:

```text
VELOCITY,0.4,0.5
```

is valid.

But:

```text
VELOCITY,NAN,0.5
VELOCITY,INF,0.5
VELOCITY,abc,0.5
```

shall be rejected.

The firmware shall also reject values exceeding configured safety limits.

---

# 27. Error Codes

The initial error code system is:

| Code | Meaning                  |
| ---: | ------------------------ |
|  `0` | No error                 |
|  `1` | Invalid command          |
|  `2` | Invalid parameter        |
|  `3` | Velocity limit exceeded  |
|  `4` | UART communication error |
|  `5` | Encoder error            |
|  `6` | Motor control error      |
|  `7` | Watchdog timeout         |

Example:

```text
ERROR,1
```

means:

```text
Invalid command
```

---

# 28. Startup Sequence

The recommended startup sequence is:

```text
Raspberry Pi Boot
       ↓
ESP32 Boot
       ↓
UART Initialization
       ↓
Pi → PING
       ↓
ESP32 → PONG
       ↓
Communication Established
       ↓
Motor System Ready
       ↓
Robot State = OFF
```

The robot must not begin autonomous movement merely because UART communication has been established.

---

# 29. Startup Motor State

At ESP32 startup:

```text
left_target_velocity  = 0
right_target_velocity = 0
left_PWM              = 0
right_PWM             = 0
```

The ESP32 shall start with motors stopped.

---

# 30. Communication Loss

If Raspberry Pi communication is lost:

```text
Raspberry Pi
     X
     │
    UART
     X
     │
   ESP32
     ↓
Watchdog timeout
     ↓
STOP
```

The ESP32 shall not continue executing the last received velocity command indefinitely.

---

# 31. Raspberry Pi Communication Failure Handling

The Raspberry Pi should also detect communication failures.

If the Raspberry Pi detects:

* No `PONG`.
* No valid `STATUS`.
* UART exception.
* Repeated packet failure.
* Unexpected ESP32 error.

the Raspberry Pi shall:

1. Log the communication failure.
2. Stop issuing normal follow commands.
3. Attempt to send `STOP` when communication is still available.
4. Transition to an appropriate safe state.

The ESP32 watchdog remains the final low-level protection.

---

# 32. Status Transmission Rate

The ESP32 may transmit `STATUS` periodically.

Initial target:

```text
STATUS rate ≈ 10–20 Hz
```

Status messages are not intended to replace the watchdog.

The watchdog must operate locally on the ESP32.

---

# 33. Example Normal Communication

```text
Pi → ESP32
PING

ESP32 → Pi
PONG

Pi → ESP32
VELOCITY,0.40,0.40

ESP32 → Pi
STATUS,0.38,0.39,1020,1032,0

Pi → ESP32
VELOCITY,0.30,0.50

ESP32 → Pi
STATUS,0.29,0.48,1042,1060,0

Pi → ESP32
STOP

ESP32 → Pi
STATUS,0.00,0.00,1050,1075,0
```

---

# 34. Example Target-Loss Communication

When the Raspberry Pi detects that the target has been lost beyond the timeout:

```text
Target Lost
     ↓
State = OFF
     ↓
STOP
     ↓
Pi → ESP32
STOP
     ↓
ESP32
Motors = 0
```

The target is then cleared by the Raspberry Pi.

The robot requires a new authentication gesture before following another person.

---

# 35. Example UART Failure

Normal operation:

```text
Pi → ESP32
VELOCITY,0.40,0.40

Pi → ESP32
VELOCITY,0.42,0.42
```

Then communication fails.

```text
Pi
 │
 X UART
 │
ESP32
 │
 └── No valid command
          ↓
       0.2 s
          ↓
     Watchdog
          ↓
       STOP
```

Expected result:

```text
Left motor  = STOP
Right motor = STOP
```

---

# 36. Protocol State

The ESP32 communication subsystem should maintain:

```text
DISCONNECTED
CONNECTED
ERROR
```

### DISCONNECTED

UART has not been successfully established.

Motor state:

```text
STOP
```

### CONNECTED

Valid communication is occurring.

Motor commands may be executed subject to safety limits.

### ERROR

A critical communication or motor-control error has occurred.

Motor state:

```text
STOP
```

Recovery behavior shall be defined by the firmware implementation.

---

# 37. Protocol Parsing

The ESP32 parser should follow:

```text
UART RX
  ↓
Receive bytes
  ↓
Detect newline
  ↓
Build message
  ↓
Parse command
  ↓
Validate fields
  ↓
Validate numerical range
  ↓
Execute command
```

Malformed packets must not directly reach the motor-control layer.

---

# 38. Separation of Communication and Motor Control

The ESP32 firmware should maintain a clear boundary:

```text
UART Parser
     ↓
Validated Command
     ↓
Motor Command Interface
     ↓
PID Controller
     ↓
PWM
```

The UART parser should not directly manipulate PWM registers.

Likewise, the PID module should not parse UART strings.

---

# 39. Raspberry Pi Software Interface

The Raspberry Pi communication module shall expose a high-level interface such as:

```python
connect()
send_velocity(left_velocity, right_velocity)
send_stop()
ping()
read_status()
close()
```

The rest of the Raspberry Pi software should not need to know the details of the UART packet format.

For example:

```text
Follow Controller
       ↓
WheelCommand
       ↓
ESP32 UART Module
       ↓
"VELOCITY,0.4,0.5"
```

---

# 40. ESP32 Software Interface

The ESP32 should separate:

```text
uart_command
motor_control
encoder
pid
```

Recommended responsibility:

| Module              | Responsibility              |
| ------------------- | --------------------------- |
| `uart_command.cpp`  | Receive and parse messages  |
| `motor_control.cpp` | Motor command/PWM interface |
| `encoder.cpp`       | Encoder acquisition         |
| `pid.cpp`           | Wheel-speed control         |
| `main.cpp`          | System scheduling           |
| `config.h`          | Configuration constants     |

---

# 41. Timing Requirements

Initial timing requirements:

| Parameter         |   Target |
| ----------------- | -------: |
| UART baud rate    |   115200 |
| Pi command rate   |   ~30 Hz |
| Command interval  |   ~33 ms |
| ESP32 watchdog    |   200 ms |
| ESP32 status rate | 10–20 Hz |
| Follow controller | 20–50 Hz |

These values are initial engineering targets and may be adjusted during validation.

---

# 42. Safety Requirements

The communication protocol shall satisfy the following:

### CP-SAFE-001

The ESP32 shall start with motors stopped.

### CP-SAFE-002

Invalid UART packets shall not directly control the motors.

### CP-SAFE-003

Velocity commands shall be range-limited.

### CP-SAFE-004

`STOP` shall have higher priority than normal velocity execution.

### CP-SAFE-005

UART communication loss shall trigger the ESP32 watchdog.

### CP-SAFE-006

Watchdog timeout shall stop both motors.

### CP-SAFE-007

The ESP32 shall not execute the last velocity command indefinitely.

### CP-SAFE-008

The Raspberry Pi shall send commands only when the robot state permits movement.

### CP-SAFE-009

Speech and HMI processing shall never block UART motor safety handling.

---

# 43. Protocol Assumptions

The initial protocol assumes:

* UART electrical levels are compatible.
* Raspberry Pi and ESP32 share GND.
* Wheel velocity units are m/s.
* Encoder direction is calibrated correctly.
* Wheel radius is known.
* Wheel separation is known.
* Motor driver accepts PWM/control signals generated by ESP32.
* The ESP32 has sufficient processing capacity for UART, encoder, PID, and PWM tasks.

---

# 44. Future Protocol Extensions

The protocol may later be extended with:

```text
SET_MODE
SET_PID
GET_CONFIG
RESET
ESTOP
BATTERY_STATUS
TEMPERATURE
MOTOR_CURRENT
HEARTBEAT
```

A binary protocol with:

* packet header,
* message ID,
* payload length,
* sequence number,
* checksum/CRC

may also be introduced if higher robustness is required.

However, the initial implementation should remain simple and observable using ASCII UART messages.

---

# 45. Final Communication Architecture

The final intended architecture is:

```text
                    Raspberry Pi 5
                         │
             ┌───────────┴───────────┐
             │                       │
       Follow Controller        State Machine
             │                       │
             └───────────┬───────────┘
                         │
                  WheelCommand
                         │
                    UART Module
                         │
                    115200 8N1
                         │
                         ▼
                       ESP32
                         │
                  UART Parser
                         │
                  Command Validation
                         │
                  ┌──────┴──────┐
                  │             │
              Left PID      Right PID
                  │             │
              Left PWM      Right PWM
                  │             │
              Left Motor    Right Motor
                  │             │
              Left Encoder Right Encoder
                  └──────┬──────┘
                         │
                     STATUS
                         │
                         ▼
                    Raspberry Pi
```

The communication architecture follows a **high-level command / low-level execution** model.

The Raspberry Pi determines **what the robot should do**, while the ESP32 determines **how the motors physically achieve the commanded wheel velocities**.

---

# 46. Protocol Summary

| Item                   | Specification              |
| ---------------------- | -------------------------- |
| Controller             | Raspberry Pi 5             |
| Motor controller       | ESP32                      |
| Interface              | UART                       |
| UART configuration     | 115200 8N1                 |
| Protocol               | ASCII, line-based          |
| Pi → ESP32             | `VELOCITY`, `STOP`, `PING` |
| ESP32 → Pi             | `STATUS`, `PONG`, `ERROR`  |
| Wheel velocity unit    | m/s                        |
| Normal command rate    | ~30 Hz                     |
| ESP32 status rate      | 10–20 Hz                   |
| Watchdog timeout       | 0.2 s                      |
| Initial motor state    | STOP                       |
| Invalid command        | Reject                     |
| Excessive velocity     | Reject/limit               |
| Communication loss     | Automatic motor STOP       |
| Target-loss stop       | Raspberry Pi → STOP        |
| Final low-level safety | ESP32 watchdog             |

---

# 47. Related Documents

This protocol should be used together with:

```text
docs/
├── 02_system_design/
│   ├── system_architecture.md
│   ├── state_machine.md
│   ├── subsystem_design.md
│   └── data_flow.md
│
├── 03_software_design/
│   ├── software_architecture.md
│   ├── module_specification.md
│   ├── interface_specification.md
│   └── configuration_specification.md
│
├── 04_hardware_design/
│   ├── hardware_architecture.md
│   ├── pinout.md
│   ├── wiring.md
│   ├── communication_protocol.md
│   └── motor_control_specification.md
│
└── 05_validation/
    ├── test_plan.md
    └── acceptance_criteria.md
```

The protocol defined here is the authoritative interface specification for **Raspberry Pi ↔ ESP32 communication**.
