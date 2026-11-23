@echo off
echo ==========================================================
echo ESP32 RSSI Monitor — Starting Dashboard
echo ==========================================================
echo.
echo IMPORTANT: Close Arduino Serial Monitor if it is open!
echo The COM port will be busy otherwise.
echo.
echo Starting Flask server at http://127.0.0.1:5000
echo Press Ctrl+C to stop.
echo.
echo Opening browser...
start "" http://127.0.0.1:5000
python app.py