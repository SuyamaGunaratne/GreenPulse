import os
import json
import ssl
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from dotenv import load_dotenv


# =====================================================
# Load environment variables
# =====================================================

load_dotenv()


AWS_IOT_ENDPOINT = os.getenv("AWS_IOT_ENDPOINT")
AWS_IOT_PORT = int(os.getenv("AWS_IOT_PORT", "8883"))

MQTT_CLIENT_ID = os.getenv(
    "MQTT_CLIENT_ID",
    "greenpulse-backend"
)

SENSOR_TOPIC = os.getenv(
    "SENSOR_TOPIC",
    "greenpulse/device/+/sensors"
)

CA_FILE = os.getenv("CA_FILE")
CERT_FILE = os.getenv("CERT_FILE")
KEY_FILE = os.getenv("KEY_FILE")


# =====================================================
# Validate configuration
# =====================================================

required_values = {
    "AWS_IOT_ENDPOINT": AWS_IOT_ENDPOINT,
    "CA_FILE": CA_FILE,
    "CERT_FILE": CERT_FILE,
    "KEY_FILE": KEY_FILE
}

for name, value in required_values.items():

    if not value:
        raise ValueError(
            f"Missing environment variable: {name}"
        )


# =====================================================
# MQTT Connected Callback
# =====================================================

def on_connect(client, userdata, flags, reason_code, properties=None):

    print()
    print("=" * 60)
    print("CONNECTED TO AWS IOT CORE")
    print("=" * 60)

    print(f"MQTT Client ID : {MQTT_CLIENT_ID}")
    print(f"Sensor Topic   : {SENSOR_TOPIC}")

    if reason_code == 0:

        print("Connection successful.")

        result, mid = client.subscribe(
            SENSOR_TOPIC,
            qos=1
        )

        if result == mqtt.MQTT_ERR_SUCCESS:

            print("Sensor topic subscription SUCCESS")

        else:

            print(
                f"Sensor topic subscription FAILED: {result}"
            )

    else:

        print(
            f"MQTT connection failed. "
            f"Reason code: {reason_code}"
        )


# =====================================================
# MQTT Disconnected Callback
# =====================================================

def on_disconnect(
    client,
    userdata,
    disconnect_flags,
    reason_code,
    properties=None
):

    print()
    print("Disconnected from AWS IoT Core.")

    print(
        f"Disconnect reason: {reason_code}"
    )


# =====================================================
# MQTT Message Callback
# =====================================================

def on_message(client, userdata, message):

    print()
    print("=" * 60)
    print("NEW SENSOR MESSAGE")
    print("=" * 60)

    print(f"Topic: {message.topic}")

    try:

        # Convert MQTT payload to text
        payload_string = message.payload.decode("utf-8")

        print()
        print("Raw payload:")
        print(payload_string)

        # Convert JSON string into Python dictionary
        sensor_data = json.loads(payload_string)

        print()
        print("Parsed sensor data:")

        print(
            json.dumps(
                sensor_data,
                indent=2
            )
        )

        # -------------------------------------------------
        # Extract values
        # -------------------------------------------------

        device_id = sensor_data.get(
            "device_id"
        )

        timestamp = sensor_data.get(
            "timestamp"
        )

        environment = sensor_data.get(
            "environment",
            {}
        )

        temperature = environment.get(
            "temperature"
        )

        humidity = environment.get(
            "humidity"
        )

        soil_moisture = environment.get(
            "soil_moisture"
        )

        soil_raw = environment.get(
            "soil_raw"
        )

        # -------------------------------------------------
        # Display extracted values
        # -------------------------------------------------

        print()
        print("Sensor Information")
        print("-" * 40)

        print(f"Device ID      : {device_id}")
        print(f"Device Time    : {timestamp}")
        print(f"Temperature    : {temperature} °C")
        print(f"Humidity       : {humidity} %")
        print(f"Soil Moisture  : {soil_moisture} %")
        print(f"Soil Raw       : {soil_raw}")

        # -------------------------------------------------
        # Backend receive time
        # -------------------------------------------------

        backend_time = datetime.now(
            timezone.utc
        ).isoformat()

        print()
        print(
            f"Backend received at: {backend_time}"
        )

        print("=" * 60)

    except json.JSONDecodeError:

        print(
            "ERROR: MQTT payload is not valid JSON."
        )

    except Exception as e:

        print(
            f"ERROR processing sensor message: {e}"
        )


# =====================================================
# Create MQTT Client
# =====================================================

client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=MQTT_CLIENT_ID
)


# =====================================================
# Assign callbacks
# =====================================================

client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect


# =====================================================
# Configure TLS
# =====================================================

client.tls_set(
    ca_certs=CA_FILE,
    certfile=CERT_FILE,
    keyfile=KEY_FILE,
    tls_version=ssl.PROTOCOL_TLS_CLIENT
)


# =====================================================
# Connect to AWS IoT Core
# =====================================================

print()
print("=" * 60)
print("GREENPULSE CLOUD BACKEND")
print("=" * 60)

print()
print(f"AWS IoT Endpoint: {AWS_IOT_ENDPOINT}")
print(f"MQTT Port       : {AWS_IOT_PORT}")
print(f"Client ID       : {MQTT_CLIENT_ID}")

print()
print("Connecting to AWS IoT Core...")


client.connect(
    AWS_IOT_ENDPOINT,
    AWS_IOT_PORT,
    keepalive=60
)


# =====================================================
# Start MQTT loop
# =====================================================

print()
print("Backend is running...")
print("Waiting for GreenPulse sensor data...")

client.loop_forever()