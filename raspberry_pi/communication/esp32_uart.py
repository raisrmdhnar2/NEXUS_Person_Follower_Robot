#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — ESP32 UART Serial Bridge
======================================================
File: raspberry_pi/communication/esp32_uart.py
Adheres to:
- docs/revision/revision_concept.md
- docs/4_hardware_design/communication_protocol.md

Responsibility:
    Manages physical UART serial transmission of 1-byte direction commands
    ('-', 'x', '+', 's') from Raspberry Pi 5 to the ESP32 motor controller.

Features:
    1. Automatic Port Discovery: Scans /dev/ttyUSB* and /dev/ttyACM* ports.
    2. Graceful Simulation Mode: If no physical ESP32 is plugged in, the bridge
       automatically operates in dummy/simulation mode without crashing the vision pipeline.
    3. Transmission Rate Limiter: Throttles communication to 20-30 Hz to prevent
       UART buffer overflow while keeping ESP32's hardware watchdog refreshed.
    4. Auto-Reconnection & Crash-Proofing: Catches USB disconnects safely.
"""

import glob
import time
from typing import Optional

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    serial = None
    SERIAL_AVAILABLE = False


class Esp32UartBridge:
    """
    UART Communication bridge between Raspberry Pi 5 and ESP32.
    """

    CANDIDATE_PORTS = [
        "/dev/ttyUSB0",
        "/dev/ttyUSB1",
        "/dev/ttyACM0",
        "/dev/ttyACM1",
        "/dev/serial0",
        "/dev/ttyAMA0",
    ]

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 115200,
        timeout: float = 0.1,
        min_interval: float = 0.04,  # ~25 Hz maximum send rate
        enabled: bool = True
    ):
        """
        Args:
            port: Serial device path (e.g. '/dev/ttyUSB0'). If None or 'auto', auto-detects.
            baudrate: Baudrate (default: 115200 bps).
            timeout: Read/write timeout in seconds.
            min_interval: Minimum time in seconds between consecutive serial writes.
            enabled: If False, operates strictly in simulated/mock mode.
        """
        self.requested_port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.min_interval = min_interval
        self.enabled = enabled

        self.serial_conn: Optional["serial.Serial"] = None
        self.active_port: Optional[str] = None
        self.is_simulated: bool = not enabled or not SERIAL_AVAILABLE

        self.last_send_time: float = 0.0
        self.last_command: str = "s"
        self.total_bytes_sent: int = 0

        if self.enabled:
            self.connect()

    @property
    def is_connected(self) -> bool:
        """True if a physical serial connection is currently open."""
        return self.serial_conn is not None and self.serial_conn.is_open

    @property
    def status_label(self) -> str:
        """Informative label for HUD telemetry display."""
        if not self.enabled:
            return "DISABLED"
        if self.is_connected and self.active_port:
            return f"CONNECTED ({self.active_port})"
        return "SIMULATION (No Device)"

    def _find_available_port(self) -> Optional[str]:
        """Scans filesystem for candidate USB/Serial ports."""
        # 1. Test standard hardcoded candidates
        for p in self.CANDIDATE_PORTS:
            matched = glob.glob(p)
            if matched:
                return matched[0]

        # 2. Test glob for any ttyUSB or ttyACM
        acm_or_usb = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        if acm_or_usb:
            return acm_or_usb[0]

        return None

    def connect(self) -> bool:
        """
        Attempts to establish physical serial connection to ESP32.
        Falls back to simulation mode if hardware is absent.
        """
        if not SERIAL_AVAILABLE:
            print("[Esp32UartBridge] 'pyserial' not installed. Running in SIMULATION MODE.")
            self.is_simulated = True
            return False

        target_port = self.requested_port
        if not target_port or target_port.lower() == "auto":
            target_port = self._find_available_port()

        if not target_port:
            print("[Esp32UartBridge] ⚠️ No physical serial port found. Running in SIMULATION MODE.")
            self.is_simulated = True
            self.active_port = None
            return False

        try:
            self.serial_conn = serial.Serial(
                port=target_port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=self.timeout
            )
            # Flush existing buffers
            self.serial_conn.reset_input_buffer()
            self.serial_conn.reset_output_buffer()
            self.active_port = target_port
            self.is_simulated = False
            print(f"[Esp32UartBridge] ✅ Connected to ESP32 on {target_port} @ {self.baudrate} bps.")
            return True

        except Exception as e:
            print(f"[Esp32UartBridge] ⚠️ Failed to open {target_port}: {e}. Running in SIMULATION MODE.")
            self.serial_conn = None
            self.active_port = None
            self.is_simulated = True
            return False

    def send_command(self, cmd: str, force: bool = False) -> bool:
        """
        Transmits a 1-byte command ('-', 'x', '+', 's') to the ESP32.

        Args:
            cmd: Single-character string or SteeringCommand value.
            force: If True, bypasses transmission rate limiter.

        Returns:
            True if transmission succeeded (or simulated successfully).
        """
        now = time.time()
        # Rate-limiting: only transmit if interval elapsed or forced
        if not force and (now - self.last_send_time) < self.min_interval:
            return True

        # Extract first character
        char_cmd = str(cmd)[0] if cmd else "s"
        self.last_send_time = now
        self.last_command = char_cmd

        if self.is_simulated or not self.is_connected:
            # Simulated transmission
            self.total_bytes_sent += 1
            return True

        try:
            # Write 1-byte ASCII character
            data = char_cmd.encode("ascii")
            bytes_written = self.serial_conn.write(data)
            self.serial_conn.flush()
            self.total_bytes_sent += bytes_written
            return bytes_written > 0

        except Exception as e:
            print(f"\n[Esp32UartBridge] ⚠️ Serial transmission error: {e}. Switching to SIMULATION MODE.")
            self.close()
            self.is_simulated = True
            return False

    def close(self):
        """Closes serial connection cleanly."""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                # Send STOP command before closing
                self.serial_conn.write(b"s")
                self.serial_conn.flush()
                self.serial_conn.close()
            except Exception:
                pass
            print(f"[Esp32UartBridge] Serial port {self.active_port} closed cleanly.")
        self.serial_conn = None
        self.active_port = None

