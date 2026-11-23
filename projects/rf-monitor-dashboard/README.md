# ESP32 RSSI Monitor Dashboard

Low-cost indoor RF experiment: an ESP32 measures Wi-Fi RSSI (dBm) and streams it over USB serial to a local Flask dashboard. The dashboard shows live readings, stores them with a manually entered distance label, and exports CSV. A MATLAB script analyses the CSV using the log-distance path-loss model.

**Distance is never calculated from RSSI. It is always a manual label entered by the experimenter.**

---

## Hardware

- ESP32 development board (any model with Wi-Fi)
- USB cable (micro-USB or USB-C, depending on board)
- Wi-Fi router (2.4 GHz recommended)
- Windows laptop
- Arduino IDE (for flashing firmware)
- MATLAB (or MATLAB Online)

---

## Wiring / Flashing

1. Connect the ESP32 to the laptop via USB.
2. Open Arduino IDE, install the ESP32 board support (Boards Manager → esp32).
3. Open `firmware/esp32_rssi/esp32_rssi.ino`.
4. Edit the top of the file: replace `YOUR_WIFI_SSID_HERE` and `YOUR_WIFI_PASSWORD_HERE` with your network credentials.
5. Select Board → ESP32 Dev Module, and the correct COM port.
6. Click **Upload**.
7. Open Serial Monitor at 115200 baud to verify output (header `TIME_MS,RSSI_DBM` followed by one line per second).

---

## Install

```
install.bat
```

This checks for Python, creates a virtual environment (optional), and installs Flask and PySerial.

---

## Run

```
run.bat
```

This starts the Flask server and opens http://127.0.0.1:5000 in your browser.

**Important:** Close Arduino Serial Monitor before connecting, otherwise the COM port will be busy.

---

## Dashboard Usage

1. Select the COM port from the dropdown (click **Refresh** if needed).
2. Set baud rate to 115200 (default).
3. Click **Connect**.
4. Enter the manual distance label (e.g., 1, 2, 3, 5, 10 m) — this is a label, not calculated from RSSI.
5. Click **Set Distance**.
6. Walk away to the desired distance, then click **Connect** (or let it keep running).
7. Watch live RSSI, the graph, and the telemetry log.
8. Click **Export CSV** to download the data.
9. Click **Clear** to reset for the next distance.

---

## Measurement Procedure

1. Place the ESP32 at the desired distance from the router.
2. Enter the distance in the dashboard (e.g., 1 m).
3. Click **Connect** and let it collect for 30–60 seconds.
4. Click **Export CSV**.
5. Click **Clear**.
6. Repeat for 2, 3, 5, 10 m.

---

## MATLAB Analysis

1. Export CSV from the dashboard.
2. Open MATLAB.
3. Run `matlab/RF_Monitor_Analysis.m`.
4. Select the CSV file when prompted.
5. View the figures:
   - A) RSSI vs time
   - B) RSSI vs distance (individual readings)
   - C) Per-distance statistics table
   - D) Mean RSSI vs distance with std error bars
   - E) Fitted model over measured data
6. A grouped-statistics CSV is saved next to the input file.

---

## Experimental Methodology

- The ESP32 connects to the Wi-Fi network and reports RSSI every second.
- RSSI is noisy due to multipath, reflections, and interference — expect ±3–10 dBm variation.
- The log-distance path-loss model is: `RSSI(d) = A + B·log10(d)`, where `n = -B/10` is the path-loss exponent.
- The fit uses mean RSSI per distance (groups with N≥2).
- Edge cases: fewer than 2 distinct distances → fit skipped with warning; N=1 groups → std undefined.

---

## Limitations

- RSSI is noisy and affected by multipath, orientation, and router characteristics.
- Distance is a manual label, not calculated from RSSI.
- The model is a simplification; real indoor propagation is more complex.
- Dashboard is local-only (127.0.0.1:5000).

---

## Tested vs Not Tested

**Tested:**
- Flask endpoints (ports, connect, disconnect, status, history, set_distance, clear, export_csv, matlab)
- CSV export header: `Time_ms,Distance_m,RSSI_dBm`
- Parser handles valid lines, header, `#` comments, blanks, malformed lines
- MATLAB script logic (reviewed for syntax and edge cases)

**Not tested:**
- Real ESP32 hardware (no physical device connected)
- Real COM port / serial device
- MATLAB execution (MATLAB not available in this environment)

---

## Project Structure

```
projects/rf-monitor-dashboard/
  app.py, README.md, requirements.txt, install.bat, run.bat
  templates/index.html
  static/style.css, static/app.js, static/chart.min.js
  matlab/RF_Monitor_Analysis.m
  firmware/esp32_rssi/esp32_rssi.ino
  tools/fake_serial_test.py
```