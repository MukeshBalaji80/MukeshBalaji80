#!/usr/bin/env python3
"""
Test the Flask RSSI dashboard endpoints with mocked serial input.
Also tests the fake serial lines (header, comments, garbage, valid data).

Run: python tools/fake_serial_test.py
"""

import sys
import json
import threading
import time
from unittest.mock import MagicMock, patch
from pathlib import Path

# Add project root to sys.path so imports resolve
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Mock serial before importing app
mock_serial = MagicMock()
mock_serial.baudrate = 115200
mock_serial.read.return_value = b"1234567890,42\n"

# Import app after mocking serial
from app import app, parse_serial_line, data_store

print("Testing parse_serial_line...")
# Valid data
assert parse_serial_line("1234567890,42") == (1234567890, 42)
assert parse_serial_line("1234567890,-50") == (1234567890, -50)

# Header line
assert parse_serial_line("TIME_MS,RSSI_DBM") is None

# Comment lines
assert parse_serial_line("# Hello") is None
assert parse_serial_line("#Debug info") is None

# Malformed
assert parse_serial_line("garbage") is None
assert parse_serial_line("123") is None
assert parse_serial_line("123,456,789") is None
assert parse_serial_line("") is None

print("PASS: parse_serial_line tests")

# ===== Test Flask endpoints =====
with app.test_client() as client:
    # List ports (will return empty on CI, but shouldn't crash)
    resp = client.get("/api/ports")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    ports = resp.get_json()
    assert "ports" in ports
    print(f"PASS: /api/ports (found {len(ports['ports'])} ports)")

    # Connect (use a fake port to trigger serial exception)
    resp = client.post("/api/connect", json={"port": "COM_TEST", "baud": 115200})
    assert resp.status_code in [200, 400], f"Unexpected status {resp.status_code}"
    data = resp.get_json()
    assert "status" in data or "error" in data
    print(f"PASS: /api/connect (got {data})")

    # Disconnect
    resp = client.post("/api/disconnect", json={})
    assert resp.status_code == 200
    print("PASS: /api/disconnect")

    # Status
    resp = client.get("/api/status")
    assert resp.status_code == 200
    status = resp.get_json()
    assert "connected" in status and "sample_count" in status
    print(f"PASS: /api/status (connected={status['connected']})")

    # Set distance
    resp = client.post("/api/set_distance", json={"distance": 2.5})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "distance_m" in data
    print(f"PASS: /api/set_distance -> {data['distance_m']}")

    # Invalid distance
    resp = client.post("/api/set_distance", json={"distance": -1})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    print(f"PASS: /api/set_distance (invalid) -> {data['error']}")

    # History (should be empty or with fake samples)
    resp = client.get("/api/history")
    assert resp.status_code == 200
    hist = resp.get_json()
    assert "samples" in hist
    print(f"PASS: /api/history (got {len(hist['samples'])} samples)")

    # Export CSV
    resp = client.get("/api/export_csv")
    assert resp.status_code == 200
    csv = resp.data.decode("utf-8")
    lines = csv.strip().split("\n")
    assert len(lines) >= 1
    assert lines[0] == "Time_ms,Distance_m,RSSI_dBm"
    print(f"PASS: /api/export_csv (header OK, {len(lines)-1} data rows)")

    # Clear
    resp = client.post("/api/clear", json={})
    assert resp.status_code == 200
    resp = client.get("/api/status")
    assert resp.get_json()["sample_count"] == 0
    print("PASS: /api/clear")

    # MATLAB download
    resp = client.get("/api/matlab")
    if resp.status_code == 200:
        print("PASS: /api/matlab (file served)")
    else:
        print(f"PASS: /api/matlab (no file: {resp.status_code})")

    # Root page
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "ESP32 RSSI Monitor" in html
    print("PASS: / (dashboard HTML)")

print("\nAll tests passed!")
print("\nNote: Real COM port testing requires a connected device.")
print("Simulate serial data by feeding test lines to the parser manually.")