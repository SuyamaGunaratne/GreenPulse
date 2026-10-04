# GreenPulse – Smart Agentic IoT Plant-Care Device

## 1. Overview

GreenPulse is an IoT plant-care system using an ESP32, DHT22, LM393 soil-moisture sensor, AWS IoT Core, secure MQTT over TLS, and a Python cloud backend.

### Current verified flow

```text
ESP32 GP001
    |
    | MQTTS / TLS :8883
    v
AWS IoT Core (ap-southeast-1)
    |
    | MQTT
    v
Python Cloud Backend
    |
    v
JSON sensor parsing
```

Current MQTT sensor topic:

```text
greenpulse/device/GP001/sensors
```

Backend subscription:

```text
greenpulse/device/+/sensors
```

---

## 2. Project Locations

Backend project:

```text
D:\CAMPUS\4Y1S\IOT\Project\GreenPulse\Backend\GreenPulse
```

Backend structure:

```text
GreenPulse/
├── app.py
├── requirements.txt
├── .env
├── certs/
│   ├── backend-certificate.pem.crt
│   ├── backend-private.pem.key
│   └── AmazonRootCA1.pem
├── venv/
└── .git/
```

The ESP32 firmware is maintained separately in the Arduino IDE project.

---

## 3. Prerequisites

### Hardware

- ESP32 development board
- DHT22
- LM393 soil-moisture sensor
- USB cable
- Jumper wires

### Software

- Arduino IDE
- ESP32 Arduino board package
- Python 3.11 or compatible Python 3 version
- AWS account with AWS IoT Core configured

---

## 4. Arduino / ESP32 Libraries

Install these from Arduino IDE Library Manager:

```text
PubSubClient
ArduinoJson
DHT sensor library
Adafruit Unified Sensor
```

The firmware also uses ESP32 networking/TLS and time functionality such as:

```cpp
WiFi
WiFiClientSecure
PubSubClient
ArduinoJson
time.h
```

---

## 5. ESP32 Hardware Connections

### DHT22

Use the wiring defined in the ESP32 firmware.

### LM393 soil sensor

Current tested wiring:

```text
LM393 VCC -> ESP32 3.3V
LM393 GND -> ESP32 GND
LM393 AO  -> ESP32 GPIO32
LM393 DO  -> Not used
```

The soil sensor currently uses the analog output.

---

## 6. AWS Configuration

AWS region:

```text
ap-southeast-1
```

Current Thing:

```text
GreenPulse-GP001
```

Device ID:

```text
GP001
```

MQTT TLS port:

```text
8883
```

The ESP32 and backend use separate AWS IoT certificates/private keys.

Do not share or commit private keys.

---

## 7. MQTT Topics

Current topic structure:

```text
greenpulse/device/<DEVICE_ID>/sensors
greenpulse/device/<DEVICE_ID>/status
greenpulse/device/<DEVICE_ID>/care
greenpulse/device/<DEVICE_ID>/alerts
```

For GP001:

```text
greenpulse/device/GP001/sensors
greenpulse/device/GP001/status
greenpulse/device/GP001/care
greenpulse/device/GP001/alerts
```

Currently active:

```text
greenpulse/device/GP001/sensors
```

Reserved for later implementation:

```text
/care
/alerts
/status
```

---

# 8. ESP32 Setup and Run

Open the GreenPulse firmware in Arduino IDE.

Select:

```text
Tools
  -> Board
  -> ESP32 Arduino
  -> ESP32 Dev Module
```

Select the ESP32 COM port. The currently tested computer uses:

```text
COM4
```

The port can be different on another computer.

Set Serial Monitor to:

```text
115200 baud
```

Upload the firmware.

The ESP32 should:

```text
1. Start
2. Connect to Wi-Fi
3. Synchronize time using NTP
4. Connect to AWS IoT Core using MQTTS
5. Read DHT22
6. Read soil sensor
7. Create JSON
8. Publish sensor data
9. Repeat
```

Example payload:

```json
{
  "device_id": "GP001",
  "timestamp": "2026-10-04T19:45:30+05:30",
  "environment": {
    "temperature": 31.4,
    "humidity": 75.3,
    "soil_moisture": 22,
    "soil_raw": 3709
  }
}
```

---

# 9. ESP32 Time Synchronization

The firmware uses:

```text
NTP server: pool.ntp.org
Timezone: UTC+05:30
```

The timestamp should look like:

```text
2026-10-04T19:45:30+05:30
```

If it shows:

```text
1970-01-01T00:00:00+05:30
```

the ESP32 clock has not synchronized successfully. Fix NTP synchronization before relying on device timestamps for historical data.

---

# 10. Verify ESP32 -> AWS IoT Core

Open:

```text
AWS Console
  -> IoT Core
  -> MQTT test client
```

Subscribe to:

```text
greenpulse/device/GP001/sensors
```

The AWS MQTT Test Client should receive the ESP32 JSON.

If it does, this part is working:

```text
ESP32
  |
  | MQTTS
  v
AWS IoT Core
```

---

# 11. Python Backend Setup

All backend commands below should be run from:

```text
D:\CAMPUS\4Y1S\IOT\Project\GreenPulse\Backend\GreenPulse
```

Open PowerShell:

```powershell
cd "D:\CAMPUS\4Y1S\IOT\Project\GreenPulse\Backend\GreenPulse"
```

Verify:

```powershell
Get-Location
```

Expected:

```text
D:\CAMPUS\4Y1S\IOT\Project\GreenPulse\Backend\GreenPulse
```

---

# 12. Create the Python Virtual Environment

Only required the first time:

```powershell
python -m venv venv
```

This creates:

```text
GreenPulse/
└── venv/
```

---

# 13. Activate the Virtual Environment

From the backend directory:

```powershell
.\venv\Scripts\Activate.ps1
```

The prompt should become similar to:

```text
(venv) PS D:\CAMPUS\4Y1S\IOT\Project\GreenPulse\Backend\GreenPulse>
```

The `(venv)` means the environment is active.

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then:

```powershell
.\venv\Scripts\Activate.ps1
```

---

# 14. Install Python Dependencies

With `(venv)` active:

```powershell
pip install -r requirements.txt
```

Current backend packages include:

```text
Flask
python-dotenv
paho-mqtt
```

Verify Paho:

```powershell
python -c "import paho.mqtt.client as mqtt; print('Paho MQTT OK')"
```

Expected:

```text
Paho MQTT OK
```

---

# 15. Backend .env Configuration

File location:

```text
D:\CAMPUS\4Y1S\IOT\Project\GreenPulse\Backend\GreenPulse\.env
```

Required configuration:

```env
AWS_IOT_ENDPOINT=YOUR_ACTUAL_AWS_IOT_ENDPOINT
AWS_IOT_PORT=8883
MQTT_CLIENT_ID=greenpulse-backend
SENSOR_TOPIC=greenpulse/device/+/sensors

CA_FILE=certs/AmazonRootCA1.pem
CERT_FILE=certs/backend-certificate.pem.crt
KEY_FILE=certs/backend-private.pem.key
```

Replace:

```text
YOUR_ACTUAL_AWS_IOT_ENDPOINT
```

with the working AWS IoT Data endpoint.

The currently working endpoint is:

```text
ahe218vtl5wnz-ats.iot.ap-southeast-1.amazonaws.com
```

Therefore the current `.env` value is:

```env
AWS_IOT_ENDPOINT=ahe218vtl5wnz-ats.iot.ap-southeast-1.amazonaws.com
```

Do not use the placeholder when starting the application.

---

# 16. Backend Certificate Files

Required files:

```text
certs/
├── AmazonRootCA1.pem
├── backend-certificate.pem.crt
└── backend-private.pem.key
```

Check them from the backend directory:

```powershell
Test-Path certs\AmazonRootCA1.pem
Test-Path certs\backend-certificate.pem.crt
Test-Path certs\backend-private.pem.key
```

Expected:

```text
True
True
True
```

Verify the certificate and private key:

```powershell
python -c "import ssl; ssl.create_default_context().load_cert_chain('certs/backend-certificate.pem.crt','certs/backend-private.pem.key'); print('Certificate + private key OK')"
```

Expected:

```text
Certificate + private key OK
```

---

# 17. Verify .env Values

Run:

```powershell
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('Endpoint:', os.getenv('AWS_IOT_ENDPOINT')); print('Port:', os.getenv('AWS_IOT_PORT')); print('Client:', os.getenv('MQTT_CLIENT_ID')); print('Topic:', os.getenv('SENSOR_TOPIC')); print('CA:', os.getenv('CA_FILE')); print('CERT:', os.getenv('CERT_FILE')); print('KEY:', os.getenv('KEY_FILE'))"
```

Expected values include:

```text
Endpoint: ahe218vtl5wnz-ats.iot.ap-southeast-1.amazonaws.com
Port: 8883
Client: greenpulse-backend
Topic: greenpulse/device/+/sensors
CA: certs/AmazonRootCA1.pem
CERT: certs/backend-certificate.pem.crt
KEY: certs/backend-private.pem.key
```

---

# 18. Start the Python Backend

Make sure:

1. You are in the GreenPulse backend directory.
2. `(venv)` is visible in PowerShell.
3. `.env` contains the real AWS endpoint.
4. The certificate files exist.

Then run:

```powershell
python app.py
```

Expected:

```text
============================================================
GREENPULSE CLOUD BACKEND
============================================================

AWS IoT Endpoint: ahe218vtl5wnz-ats.iot.ap-southeast-1.amazonaws.com
MQTT Port       : 8883
Client ID       : greenpulse-backend

Connecting to AWS IoT Core...

Backend is running...
Waiting for GreenPulse sensor data...

============================================================
CONNECTED TO AWS IOT CORE
============================================================
MQTT Client ID : greenpulse-backend
Sensor Topic   : greenpulse/device/+/sensors
Connection successful.
Sensor topic subscription SUCCESS
```

Leave this terminal running.

---

# 19. Verify Backend Receives Sensor Data

When the ESP32 publishes, the backend should show:

```text
============================================================
NEW SENSOR MESSAGE
============================================================
Topic: greenpulse/device/GP001/sensors

Raw payload:
{"device_id":"GP001", ...}

Parsed sensor data:
{
  "device_id": "GP001",
  "timestamp": "...",
  "environment": {
    "temperature": 31,
    "humidity": 76.4,
    "soil_moisture": 0,
    "soil_raw": 4095
  }
}

Sensor Information
----------------------------------------
Device ID      : GP001
Device Time    : ...
Temperature    : 31 °C
Humidity       : 76.4 %
Soil Moisture  : 0 %
Soil Raw       : 4095

Backend received at: ...
============================================================
```

This confirms:

```text
ESP32
  ↓ MQTTS
AWS IoT Core
  ↓ MQTT
Python Backend
  ↓
JSON parsing
```

---

# 20. Test Without ESP32

You can test the backend directly from AWS IoT MQTT Test Client.

Publish to:

```text
greenpulse/device/GP001/sensors
```

Example:

```json
{
  "device_id": "GP001",
  "timestamp": "2026-10-04T19:40:00+05:30",
  "environment": {
    "temperature": 30.0,
    "humidity": 70.0,
    "soil_moisture": 50,
    "soil_raw": 3000
  }
}
```

If Python prints the message, the backend MQTT subscription is working.

---

# 21. Normal Daily Startup

Once setup is complete, you do NOT need to recreate the virtual environment.

Every time you want to run the backend:

```powershell
cd "D:\CAMPUS\4Y1S\IOT\Project\GreenPulse\Backend\GreenPulse"
```

Then:

```powershell
.\venv\Scripts\Activate.ps1
```

Then:

```powershell
python app.py
```

So the normal three commands are:

```powershell
cd "D:\CAMPUS\4Y1S\IOT\Project\GreenPulse\Backend\GreenPulse"
.\venv\Scripts\Activate.ps1
python app.py
```

---

# 22. Stop the Backend

In the backend terminal:

```text
Ctrl + C
```

Then the Python process stops.

To start it again:

```powershell
python app.py
```

---

# 23. Recommended Complete Test Order

## Terminal / Device 1 – ESP32

1. Open Arduino IDE.
2. Select ESP32 Dev Module.
3. Select the correct COM port.
4. Upload firmware.
5. Open Serial Monitor at 115200.
6. Confirm Wi-Fi.
7. Confirm NTP.
8. Confirm AWS IoT.
9. Confirm sensor publishing.

## AWS Console – MQTT Test Client

Subscribe:

```text
greenpulse/device/GP001/sensors
```

Confirm messages arrive.

## Terminal / Device 2 – Python Backend

Run:

```powershell
cd "D:\CAMPUS\4Y1S\IOT\Project\GreenPulse\Backend\GreenPulse"
.\venv\Scripts\Activate.ps1
python app.py
```

Confirm:

```text
CONNECTED TO AWS IOT CORE
Sensor topic subscription SUCCESS
NEW SENSOR MESSAGE
```

---

# 24. Common Problems

## `ModuleNotFoundError: No module named 'paho'`

Activate the virtual environment:

```powershell
.\venv\Scripts\Activate.ps1
```

Then:

```powershell
pip install -r requirements.txt
```

---

## `socket.gaierror: [Errno 11001] getaddrinfo failed`

The AWS IoT endpoint is invalid or still a placeholder.

Check:

```powershell
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('AWS_IOT_ENDPOINT'))"
```

It must print the real AWS endpoint.

---

## `ssl.SSLError: [SSL] PEM lib`

Check the certificate files:

```text
certs/AmazonRootCA1.pem
certs/backend-certificate.pem.crt
certs/backend-private.pem.key
```

Then run:

```powershell
python -c "import ssl; ssl.create_default_context().load_cert_chain('certs/backend-certificate.pem.crt','certs/backend-private.pem.key'); print('Certificate + private key OK')"
```

---

## Backend connects but receives nothing

Check the AWS IoT MQTT Test Client.

Subscribe to:

```text
greenpulse/device/GP001/sensors
```

If AWS receives ESP32 data but Python does not, check:

```text
1. Backend certificate
2. AWS IoT policy
3. iot:Subscribe
4. iot:Receive
5. MQTT topic
6. client.on_message callback
```

---

## Backend repeatedly disconnects

Check that the backend IoT policy matches the MQTT subscription.

The backend requires:

```text
iot:Connect
iot:Subscribe
iot:Receive
```

The current MQTT subscription is:

```text
greenpulse/device/+/sensors
```

A policy supporting multiple device IDs can use AWS policy wildcard `*`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iot:Connect",
      "Resource": "arn:aws:iot:ap-southeast-1:*:client/greenpulse-backend"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Subscribe",
      "Resource": "arn:aws:iot:ap-southeast-1:*:topicfilter/greenpulse/device/*/sensors"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Receive",
      "Resource": "arn:aws:iot:ap-southeast-1:*:topic/greenpulse/device/*/sensors"
    }
  ]
}
```

Important distinction:

```text
MQTT subscription:
greenpulse/device/+/sensors

AWS IoT policy resource:
greenpulse/device/*/sensors
```

---

# 25. Security

Never commit these files/secrets:

```text
.env
backend-private.pem.key
ESP32 private key
LLM API keys
Weather API keys
Email credentials
```

Recommended `.gitignore`:

```gitignore
.env
venv/
__pycache__/
*.pyc
certs/*private*.key
```

The backend and ESP32 should use separate AWS IoT certificates/private keys.

---

# 26. Current Project Status

Completed:

```text
[✓] ESP32 setup
[✓] DHT22 sensor
[✓] LM393 soil sensor
[✓] AWS IoT Thing
[✓] ESP32 AWS IoT certificate
[✓] ESP32 -> AWS IoT Core
[✓] MQTT over TLS
[✓] Backend certificate
[✓] Backend TLS connection
[✓] Backend -> AWS IoT Core
[✓] Backend MQTT subscription
[✓] Backend receives sensor JSON
[✓] Backend parses sensor JSON
```

Next implementation stages:

```text
[ ] Sensor data storage
[ ] Weather API
[ ] LLM framework/API
[ ] Build plant/environment context
[ ] Generate care recommendation
[ ] Publish /care
[ ] Publish /alerts
[ ] ESP32 subscribes to /care and /alerts
[ ] RGB urgency indicator
[ ] Node-RED dashboard
[ ] Complete end-to-end agentic flow
```

---

# 27. Planned GreenPulse End-to-End Architecture

```text
                    ┌──────────────────────┐
                    │      ESP32 GP001     │
                    │                      │
                    │ DHT22                │
                    │ Soil Moisture        │
                    └──────────┬───────────┘
                               │
                               │ MQTTS :8883
                               ▼
                    ┌──────────────────────┐
                    │    AWS IoT Core      │
                    │                      │
                    │ /sensors             │
                    │ /status              │
                    │ /care                │
                    │ /alerts              │
                    └──────────┬───────────┘
                               │
                               │ MQTT
                               ▼
                    ┌──────────────────────┐
                    │ Python Cloud Backend │
                    │                      │
                    │ Data Processing      │
                    │ Storage              │
                    │ Weather API          │
                    │ LLM                  │
                    └───────┬───────┬──────┘
                            │       │
                    Weather API     LLM
                            │       │
                            └───┬───┘
                                │
                                ▼
                       Care Recommendation
                                │
                                ▼
                         AWS IoT /care
                                │
                                ▼
                             ESP32
                                │
                         ┌──────┴──────┐
                         │             │
                       Display       RGB LED

                    Node-RED Dashboard
                           ▲
                           │
                     MQTT / Backend
```

---

# 28. Quick Start – Short Version

For a machine that has already been configured:

### ESP32

Run the firmware from Arduino IDE.

### Backend

Open PowerShell:

```powershell
cd "D:\CAMPUS\4Y1S\IOT\Project\GreenPulse\Backend\GreenPulse"
```

Activate:

```powershell
.\venv\Scripts\Activate.ps1
```

Run:

```powershell
python app.py
```

Expected:

```text
CONNECTED TO AWS IOT CORE
Sensor topic subscription SUCCESS
NEW SENSOR MESSAGE
```

Current verified core path:

```text
ESP32
  ↓
MQTTS :8883
  ↓
AWS IoT Core
  ↓
MQTT
  ↓
Python Backend
  ↓
Sensor JSON
```
