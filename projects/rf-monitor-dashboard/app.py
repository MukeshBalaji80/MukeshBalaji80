#!/usr/bin/env python3
"""
Flask backend for ESP32 RSSI Monitor Dashboard

Endpoints:
  /                   - Serves the dashboard HTML
  /api/ports          - List available COM ports
  /api/connect        - Connect to a serial port (POST: port, baud)
  /api/disconnect     - Disconnect from current port (POST)
  /api/status         - Current connection status + latest reading
  /api/history        - All stored samples (Time_ms, Distance_m, RSSI_dBm)
  /api/set_distance   - Set the manual distance label for new samples (POST: distance)
  /api/clear          - Clear all stored data (POST)
  /api/export_csv     - Download CSV file with header Time_ms,Distance_m,RSSI_dBm
  /api/matlab         - Download the MATLAB analysis script
"""

import json
import threading
import time
import serial
import serial.tools.list_ports
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty
from flask import Flask, render_template, jsonify, request, send_file, make_response, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ===== MATLAB Output Graph Storage =====
# Users upload actual MATLAB output graphs here after running RF_Monitor_Analysis.m
# These are REAL experimental results — never fabricated. Stored as files.
MATLAB_OUTPUTS_DIR = Path(__file__).parent / "static" / "matlab_outputs"
MATLAB_OUTPUTS_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ===== Thread-safe data store =====
class DataStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._samples = []           # list of dicts: {Time_ms, Distance_m, RSSI_dBm}
        self._distance = 1.0         # current manual distance label (meters)
        self._collection_start_ms = None  # absolute millis when collection started

    def add_sample(self, time_ms, rssi_dbm):
        with self._lock:
            if self._collection_start_ms is None:
                self._collection_start_ms = time_ms
            # Store elapsed time relative to collection start
            elapsed = time_ms - self._collection_start_ms
            self._samples.append({
                "Time_ms": elapsed,
                "Distance_m": self._distance,
                "RSSI_dBm": rssi_dbm
            })

    def get_samples(self):
        with self._lock:
            return list(self._samples)

    def set_distance(self, distance_m):
        with self._lock:
            try:
                d = float(distance_m)
                if d <= 0:
                    return False, "Distance must be > 0"
                self._distance = d
                return True, f"Distance set to {d:.2f} m"
            except (ValueError, TypeError):
                return False, "Invalid distance value"

    def get_distance(self):
        with self._lock:
            return self._distance

    def clear(self):
        with self._lock:
            self._samples.clear()
            self._collection_start_ms = None

    def sample_count(self):
        with self._lock:
            return len(self._samples)

    def get_csv(self):
        with self._lock:
            lines = ["Time_ms,Distance_m,RSSI_dBm"]
            for s in self._samples:
                lines.append(f"{s['Time_ms']},{s['Distance_m']},{s['RSSI_dBm']}")
            return "\n".join(lines)


# Global instances
data_store = DataStore()
serial_thread = None
serial_port = None
serial_queue = Queue()  # raw lines from serial thread
serial_lock = threading.Lock()


# ===== Serial reader thread =====
def serial_reader(port, baud, queue, stop_event):
    """Background thread that reads lines from the serial port and pushes them to a queue."""
    ser = None
    try:
        ser = serial.Serial(port, baud, timeout=1)
        # Give ESP32 a moment to settle
        time.sleep(0.2)
        ser.reset_input_buffer()

        while not stop_event.is_set():
            try:
                line_bytes = ser.readline()
                if not line_bytes:
                    continue
                line = line_bytes.decode("utf-8", errors="ignore").strip()
                if line:
                    queue.put(line)
            except (serial.SerialException, OSError) as e:
                # Port probably unplugged
                queue.put(f"# ERROR: {e}")
                break
    except serial.SerialException as e:
        queue.put(f"# ERROR opening port: {e}")
    finally:
        if ser and ser.is_open:
            try:
                ser.close()
            except Exception:
                pass


def parse_serial_line(line):
    """Parse a single serial line. Returns (time_ms, rssi_dbm) or None if not a data line."""
    line = line.strip()
    if not line:
        return None
    if line.startswith("#"):  # comment/debug line
        return None
    if line.upper().startswith("TIME_MS"):  # header line
        return None
    parts = line.split(",")
    if len(parts) != 2:
        return None
    try:
        time_ms = int(parts[0])
        rssi_dbm = int(parts[1])
        return time_ms, rssi_dbm
    except ValueError:
        return None


def process_serial_queue():
    """Called from the main thread (via a background task) to drain the queue."""
    while not serial_queue.empty():
        try:
            line = serial_queue.get_nowait()
        except Empty:
            break

        parsed = parse_serial_line(line)
        if parsed:
            time_ms, rssi = parsed
            data_store.add_sample(time_ms, rssi)
        else:
            # Could log debug lines here if desired
            pass


# ===== Flask Routes =====

@app.route("/")
def index():
    """Serve the main dashboard page."""
    # Read MATLAB source to inject inline (single source of truth)
    matlab_path = Path(__file__).parent / "matlab" / "RF_Monitor_Analysis.m"
    matlab_code = ""
    if matlab_path.exists():
        matlab_code = matlab_path.read_text(encoding="utf-8")
    return render_template("index.html", matlab_code=matlab_code)


@app.route("/api/ports")
def api_ports():
    """List available COM ports."""
    ports = []
    for p in serial.tools.list_ports.comports():
        ports.append({
            "device": p.device,
            "description": p.description,
            "hwid": p.hwid
        })
    return jsonify({"ports": ports})


@app.route("/api/connect", methods=["POST"])
def api_connect():
    """Open a serial port and start the reader thread."""
    global serial_thread, serial_port

    payload = request.get_json(silent=True) or {}
    port = payload.get("port")
    baud = int(payload.get("baud", 115200))

    if not port:
        return jsonify({"error": "Missing 'port' parameter"}), 400

    with serial_lock:
        if serial_thread and serial_thread.is_alive():
            return jsonify({"error": "Already connected. Disconnect first."}), 400

        stop_event = threading.Event()
        serial_queue.queue.clear()  # clear any stale lines

        serial_thread = threading.Thread(
            target=serial_reader,
            args=(port, baud, serial_queue, stop_event),
            daemon=True
        )
        serial_thread.stop_event = stop_event  # attach for later use
        serial_port = port
        serial_thread.start()

    return jsonify({"status": "connected", "port": port, "baud": baud})


@app.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    """Close the serial port and stop the reader thread."""
    global serial_thread, serial_port

    with serial_lock:
        if not serial_thread or not serial_thread.is_alive():
            serial_port = None
            return jsonify({"status": "already disconnected"})

        serial_thread.stop_event.set()
        serial_thread.join(timeout=2)
        serial_port = None

    return jsonify({"status": "disconnected"})


@app.route("/api/status")
def api_status():
    """Return current connection status and latest reading."""
    process_serial_queue()  # drain any pending lines

    latest = None
    samples = data_store.get_samples()
    if samples:
        latest = samples[-1]

    return jsonify({
        "connected": serial_thread is not None and serial_thread.is_alive(),
        "port": serial_port,
        "distance_m": data_store.get_distance(),
        "sample_count": len(samples),
        "latest": latest
    })


@app.route("/api/history")
def api_history():
    """Return all stored samples."""
    process_serial_queue()
    return jsonify({"samples": data_store.get_samples()})


@app.route("/api/set_distance", methods=["POST"])
def api_set_distance():
    """Update the manual distance label for subsequent samples."""
    payload = request.get_json(silent=True) or {}
    distance = payload.get("distance")
    if distance is None:
        return jsonify({"error": "Missing 'distance' parameter"}), 400

    ok, msg = data_store.set_distance(distance)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"status": "ok", "message": msg, "distance_m": data_store.get_distance()})


@app.route("/api/clear", methods=["POST"])
def api_clear():
    """Clear all stored samples."""
    data_store.clear()
    return jsonify({"status": "cleared"})


@app.route("/api/export_csv")
def api_export_csv():
    """Download samples as CSV with exact header: Time_ms,Distance_m,RSSI_dBm"""
    csv_data = data_store.get_csv()
    response = make_response(csv_data)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=rssi_data.csv"
    return response


@app.route("/api/matlab")
def api_matlab():
    """Download the MATLAB analysis script."""
    matlab_path = Path(__file__).parent / "matlab" / "RF_Monitor_Analysis.m"
    if not matlab_path.exists():
        return jsonify({"error": "MATLAB script not found"}), 404
    return send_file(matlab_path, as_attachment=True, download_name="RF_Monitor_Analysis.m")


# ===== MATLAB Output Graphs (actual results from running the script) =====

@app.route("/api/matlab_graphs")
def api_matlab_graphs():
    """List uploaded MATLAB output graph images (real results only — never fabricated)."""
    graphs = []
    for f in sorted(MATLAB_OUTPUTS_DIR.iterdir()):
        if f.is_file() and allowed_file(f.name):
            graphs.append({
                "filename": f.name,
                "url": f"/api/matlab_graphs/file/{f.name}",
                "size_kb": round(f.stat().st_size / 1024, 1),
                "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
    return jsonify({"graphs": graphs})


@app.route("/api/matlab_graphs/file/<path:filename>")
def api_matlab_graph_file(filename):
    """Serve a specific uploaded MATLAB output image."""
    filename = secure_filename(filename)
    filepath = MATLAB_OUTPUTS_DIR / filename
    if not filepath.exists():
        return jsonify({"error": "Image not found"}), 404
    return send_from_directory(MATLAB_OUTPUTS_DIR, filename)


@app.route("/api/matlab_graphs/upload", methods=["POST"])
def api_matlab_graphs_upload():
    """Upload actual MATLAB output graph images. These are REAL results — never fabricated."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed (use png, jpg, jpeg, gif, webp, svg)"}), 400

    filename = secure_filename(file.filename)
    dest = MATLAB_OUTPUTS_DIR / filename
    file.save(dest)
    return jsonify({
        "status": "uploaded",
        "filename": filename,
        "url": f"/api/matlab_graphs/file/{filename}",
        "size_kb": round(dest.stat().st_size / 1024, 1),
        "message": "MATLAB output graph added to dashboard. These are real experimental results.",
    })


@app.route("/api/matlab_graphs/delete/<path:filename>", methods=["POST"])
def api_matlab_graphs_delete(filename):
    """Delete an uploaded MATLAB output graph."""
    filename = secure_filename(filename)
    filepath = MATLAB_OUTPUTS_DIR / filename
    if not filepath.exists():
        return jsonify({"error": "Image not found"}), 404
    filepath.unlink()
    return jsonify({"status": "deleted", "filename": filename})


# ===== Main =====
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)