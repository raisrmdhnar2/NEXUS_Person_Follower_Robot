from collections import deque
import sys
import time
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore
import serial

# Configure your serial port
PORT = "/dev/ttyACM0"  # Update this to your ESP32-S3 serial port
BAUD_RATE = 115200

# Target frequency settings (25 Hz)
FREQUENCY = 25
INTERVAL = 1.0 / FREQUENCY

# Global Data Send Variable
RotationData = 100

# Setup buffers for real-time plotting (keep last 250 points = 10 seconds of data)
BUFFER_SIZE = 250
time_buffer = deque(maxlen=BUFFER_SIZE)

# Separate buffers for the 4 incoming values: [dt, P, I, D]
dt_buffer = deque(maxlen=BUFFER_SIZE)
p_buffer = deque(maxlen=BUFFER_SIZE)
i_buffer = deque(maxlen=BUFFER_SIZE)
d_buffer = deque(maxlen=BUFFER_SIZE)

lpwm_buffer = deque(maxlen=BUFFER_SIZE)
rpwm_buffer = deque(maxlen=BUFFER_SIZE)

start_time = time.time()

next_send_time = time.time()


def main():
  global RotationData

  print(f"Connecting to {PORT} at {BAUD_RATE} baud...")
  try:
    ser = serial.Serial(PORT, BAUD_RATE, timeout=0.001)
  except serial.SerialException as e:
    print(f"Error opening serial port: {e}")
    return

  time.sleep(2)
  ser.reset_input_buffer()
  print(
      f"Connected! Running at {FREQUENCY} Hz. Opening 4-channel live graph"
      " window..."
  )

  # ---------------------------------------------------------
  # GUI / PyQtGraph Setup
  # ---------------------------------------------------------
  app = pg.mkQApp("ESP32-S3 PID & Delta Live Graph")

  win = pg.GraphicsLayoutWidget(show=True, title="ESP32-S3 Telemetry Live Plot")
  win.resize(900, 500)

  plot = win.addPlot(title="Real-Time PID & Delta Telemetry (25 Hz)")
  plot.setLabel("left", "Value")
  plot.setLabel("bottom", "Time", units="s")
  plot.showGrid(x=True, y=True)
  plot.addLegend()  # Adds a legend to identify the 4 curves

  # Create 4 distinct curves with different colors
  curve_dt = plot.plot(
      pen=pg.mkPen(color=(0, 255, 128), width=2), name="Delta Time (dt)"
  )
  curve_p = plot.plot(
      pen=pg.mkPen(color=(0, 191, 255), width=2), name="Proportional (P)"
  )
  curve_i = plot.plot(
      pen=pg.mkPen(color=(255, 105, 180), width=2), name="Integral (I)"
  )
  curve_d = plot.plot(
      pen=pg.mkPen(color=(255, 215, 0), width=2), name="Derivative (D)"
  )
  curve_lpwm = plot.plot(
      pen=pg.mkPen(color=(255, 0, 0), width=2), name="Left Motor PWM"
  )
  curve_rpwm = plot.plot(
      pen=pg.mkPen(color=(0, 255, 0), width=2), name="Right Motor PWM"
  )

  def update_loop():
    global RotationData, next_send_time

    current_time = time.time()

    # 1. SENDING DATA (25 times per second)
    if current_time >= next_send_time:
      message = f"{RotationData:.2f}\n"
      ser.write(message.encode("utf-8"))
      next_send_time += INTERVAL

    # 2. RECEIVING & SPLITTING DATA BY SPACE
    if ser.in_waiting > 0:
      raw_line = ser.readline()
      if raw_line:
        try:
          line_str = raw_line.decode("utf-8").strip()
          if line_str:
            tokens = line_str.split(" ")

            if len(tokens) >= 2 and len(tokens) < 4:  # Expecting at least 2 tokens for motor PWM values
              left_motor_pwm = float(tokens[0])
              right_motor_pwm = float(tokens[1])

              print(
                  f"Received -> Left Motor PWM: {left_motor_pwm}, Right Motor"
                  f" PWM: {right_motor_pwm}"
              )

              lpwm_buffer.append(left_motor_pwm)
              rpwm_buffer.append(right_motor_pwm)

              # Update all 4 graph curves
              t_list = list(time_buffer)
              curve_dt.setData(t_list, list(dt_buffer))
              curve_p.setData(t_list, list(p_buffer))
              curve_i.setData(t_list, list(i_buffer))
              curve_d.setData(t_list, list(d_buffer))
              curve_lpwm.setData(t_list, list(lpwm_buffer))
              curve_rpwm.setData(t_list, list(rpwm_buffer))

            # Expecting at least 4 tokens: [dt, P, I, D]
            if len(tokens) >= 4:
              dt_val = float(tokens[0])
              p_val = float(tokens[1])
              i_val = float(tokens[2])
              d_val = float(tokens[3])

              print(
                  f"Received -> dt: {dt_val}, P: {p_val}, I: {i_val}, D:"
                  f" {d_val}"
              )

              # Append to buffers
              t_stamp = current_time - start_time
              time_buffer.append(t_stamp)
              dt_buffer.append(dt_val)
              p_buffer.append(p_val)
              i_buffer.append(i_val)
              d_buffer.append(d_val)

              # Modify mock target data for testing flow
              totalval = p_val + i_val + d_val
              print(f"Total PID Value: {totalval}")
              if totalval > 0:
                RotationData = RotationData + 0.1
              elif totalval < 0:
                RotationData = RotationData - 0.1
              

        except (UnicodeDecodeError, ValueError) as e:
          print(f"Error decoding or parsing line: {raw_line}. Error: {e}")
          pass

  # Setup high-speed Qt Timer
  timer = QtCore.QTimer()
  timer.timeout.connect(update_loop)
  timer.start(2)

  try:
    sys.exit(app.exec())
  except KeyboardInterrupt:
    print("\nExiting program and closing serial port.")
  finally:
    ser.close()


if __name__ == "__main__":
  main()