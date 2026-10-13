"""GreenPulse cloud backend.

Receives ESP32 sensor messages through AWS IoT Core, obtains cached Open-Meteo
weather, performs rule-based plant-care assessment, and stores readings in
DynamoDB. Groq/LangChain recommendations run in a background worker so an
LLM API call does not block the Paho MQTT message callback.
"""

import json
import logging
import os
import queue
import ssl
import threading
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
import paho.mqtt.client as mqtt
import requests
from dotenv import load_dotenv
from plant_care import assess_plant_care

load_dotenv()

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("paho").setLevel(logging.DEBUG)

# Optional LLM integration
try:
    from llm_care import care_recommendation as generate_care_recommendation
    LLM_IMPORT_ERROR = None
except Exception as import_error:
    generate_care_recommendation = None
    LLM_IMPORT_ERROR = import_error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AWS_IOT_ENDPOINT = os.getenv("AWS_IOT_ENDPOINT")
AWS_IOT_PORT = int(os.getenv("AWS_IOT_PORT", "8883"))
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "greenpulse-backend")
SENSOR_TOPIC = os.getenv("SENSOR_TOPIC", "greenpulse/device/+/sensors")
CA_FILE = os.getenv("CA_FILE")
CERT_FILE = os.getenv("CERT_FILE")
KEY_FILE = os.getenv("KEY_FILE")

AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "GreenPluseSensorReadings")
AWS_PROFILE = os.getenv("AWS_PROFILE", "greenpulse-local")

WEATHER_API_URL = os.getenv(
    "WEATHER_API_URL", "https://api.open-meteo.com/v1/forecast"
)
WEATHER_LATITUDE = float(os.getenv("WEATHER_LATITUDE", "6.9271"))
WEATHER_LONGITUDE = float(os.getenv("WEATHER_LONGITUDE", "79.8612"))
WEATHER_TIMEZONE = os.getenv("WEATHER_TIMEZONE", "Asia/Colombo")
WEATHER_TEMPERATURE_UNIT = os.getenv("WEATHER_TEMPERATURE_UNIT", "celsius")
WEATHER_REFRESH_SECONDS = int(os.getenv("WEATHER_REFRESH_SECONDS", "900"))

LLM_COOLDOWN_SECONDS = int(os.getenv("LLM_COOLDOWN_SECONDS", "900"))
LLM_QUEUE_MAX_SIZE = int(os.getenv("LLM_QUEUE_MAX_SIZE", "50"))

required_values = {
    "AWS_IOT_ENDPOINT": AWS_IOT_ENDPOINT,
    "CA_FILE": CA_FILE,
    "CERT_FILE": CERT_FILE,
    "KEY_FILE": KEY_FILE,
}
for name, value in required_values.items():
    if not value:
        raise ValueError(f"Missing environment variable: {name}")

# ---------------------------------------------------------------------------
# DynamoDB initialization
# ---------------------------------------------------------------------------
print("Initializing DynamoDB connection...")
aws_session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
dynamodb = aws_session.resource("dynamodb")
sensor_table = dynamodb.Table(DYNAMODB_TABLE)
print(f"DynamoDB Region : {AWS_REGION}")
print(f"DynamoDB Table  : {DYNAMODB_TABLE}")
print(f"AWS Profile     : {AWS_PROFILE}")

# ---------------------------------------------------------------------------
# Weather cache and refresh
# ---------------------------------------------------------------------------
weather_lock = threading.Lock()
latest_weather = None


def fetch_weather():
    """Fetch and validate current weather conditions from Open-Meteo."""
    params = {
        "latitude": WEATHER_LATITUDE,
        "longitude": WEATHER_LONGITUDE,
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "precipitation,weather_code,wind_speed_10m"
        ),
        "temperature_unit": WEATHER_TEMPERATURE_UNIT,
        "timezone": WEATHER_TIMEZONE,
    }
    response = requests.get(WEATHER_API_URL, params=params, timeout=10)
    response.raise_for_status()
    current = response.json().get("current")
    if not isinstance(current, dict):
        raise ValueError("Weather response has no current data.")

    return {
        "weather_time": current["time"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "temperature_c": current["temperature_2m"],
        "humidity_percent": current["relative_humidity_2m"],
        "apparent_temperature_c": current["apparent_temperature"],
        "precipitation_mm": current["precipitation"],
        "weather_code": current["weather_code"],
        "wind_speed_kmh": current["wind_speed_10m"],
        "latitude": WEATHER_LATITUDE,
        "longitude": WEATHER_LONGITUDE,
        "timezone": WEATHER_TIMEZONE,
    }


def weather_refresh_loop():
    """Refresh weather in a daemon thread, independently of MQTT callbacks."""
    global latest_weather
    while True:
        try:
            new_weather = fetch_weather()
            with weather_lock:
                latest_weather = new_weather
            print("\n" + "=" * 60)
            print("WEATHER REFRESH SUCCESS")
            print("=" * 60)
            print(f"Weather time : {new_weather['weather_time']}")
            print(f"Fetched at   : {new_weather['fetched_at']}")
            print(f"Temperature  : {new_weather['temperature_c']} °C")
            print(f"Humidity     : {new_weather['humidity_percent']} %")
            print(f"Precipitation: {new_weather['precipitation_mm']} mm")
            print(f"Weather code : {new_weather['weather_code']}")
            print("=" * 60)
        except Exception as error:
            print(f"WEATHER REFRESH FAILED: {error}")
            print("Sensor processing will continue.")
        time.sleep(WEATHER_REFRESH_SECONDS)


def get_latest_weather():
    """Return a copy of the latest successfully fetched weather snapshot."""
    with weather_lock:
        return dict(latest_weather) if latest_weather is not None else None

# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------
def _dynamodb_safe(value):
    """Convert floats recursively to Decimal for DynamoDB compatibility."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {str(key): _dynamodb_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_dynamodb_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_dynamodb_safe(item) for item in value]
    return value


def save_sensor_reading(
    device_id,
    timestamp,
    temperature,
    humidity,
    soil_moisture,
    soil_raw,
    backend_time,
    mqtt_topic,
    weather,
    care_assessment=None,
):
    """Store one sensor reading and its rule-based context in DynamoDB."""
    reading_id = (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        + "#"
        + uuid.uuid4().hex
    )
    item = {
        "device_id": device_id,
        "reading_id": reading_id,
        "timestamp": timestamp,
        "backend_received_at": backend_time,
        "mqtt_topic": mqtt_topic,
        "temperature": Decimal(str(temperature)),
        "humidity": Decimal(str(humidity)),
        "soil_moisture": Decimal(str(soil_moisture)),
        "soil_raw": Decimal(str(soil_raw)),
    }
    if weather is not None:
        item["weather"] = _dynamodb_safe(weather)
    if care_assessment is not None:
        item["care_assessment"] = _dynamodb_safe(care_assessment)
    sensor_table.put_item(Item=item)
    return reading_id


def save_ai_recommendation(device_id, reading_id, recommendation):
    """Attach a completed AI recommendation to its original sensor reading."""
    sensor_table.update_item(
        Key={"device_id": device_id, "reading_id": reading_id},
        UpdateExpression=(
            "SET care_recommendation = :recommendation, "
            "care_recommendation_generated_at = :generated_at"
        ),
        ExpressionAttributeValues={
            ":recommendation": _dynamodb_safe(recommendation),
            ":generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

# ---------------------------------------------------------------------------
# Background LLM worker
# ---------------------------------------------------------------------------
llm_queue = queue.Queue(maxsize=LLM_QUEUE_MAX_SIZE)
llm_cooldown_lock = threading.Lock()
last_llm_enqueued_by_device = {}


def queue_ai_recommendation(
    device_id, reading_id, sensor_data, weather, care_assessment
):
    """Queue AI work without blocking the Paho MQTT callback."""
    if generate_care_recommendation is None:
        print("LLM unavailable; sensor reading saved without AI recommendation.")
        if LLM_IMPORT_ERROR:
            logging.warning("LLM import failed: %s", LLM_IMPORT_ERROR)
        return

    risks = care_assessment.get("detected_risks", [])
    needs_attention = care_assessment.get("care_status") == "ATTENTION" or bool(risks)
    if not needs_attention:
        print("AI recommendation skipped: no care risks detected.")
        return

    now = time.monotonic()
    with llm_cooldown_lock:
        last_enqueued = last_llm_enqueued_by_device.get(device_id, 0)
        if now - last_enqueued < LLM_COOLDOWN_SECONDS:
            print(
                "AI recommendation skipped: cooldown active "
                f"({LLM_COOLDOWN_SECONDS} seconds per device)."
            )
            return
        last_llm_enqueued_by_device[device_id] = now

    job = {
        "device_id": device_id,
        "reading_id": reading_id,
        "sensor_data": sensor_data,
        "weather": weather,
        "assessment": care_assessment,
    }
    try:
        llm_queue.put_nowait(job)
        print("AI recommendation queued for background processing.")
    except queue.Full:
        with llm_cooldown_lock:
            last_llm_enqueued_by_device.pop(device_id, None)
        print("AI recommendation queue is full; skipping this request.")


def llm_worker_loop():
    """Generate Groq recommendations and store them outside the MQTT callback."""
    if generate_care_recommendation is None:
        print("LLM worker not started: llm_care could not be imported.")
        return

    print("LangChain + Groq background worker started.")
    while True:
        job = llm_queue.get()
        try:
            device_id = job["device_id"]
            print(f"Generating Groq recommendation for {device_id}...")
            recommendation = generate_care_recommendation(
                sensor_data=job["sensor_data"],
                weather=job["weather"],
                assessment=job["assessment"],
            )
            if not isinstance(recommendation, dict):
                raise ValueError("LLM recommendation must be a dictionary.")

            recommendation["message_type"] = "groq_ai_recommendation"
            recommendation["generated_at"] = datetime.now(timezone.utc).isoformat()
            save_ai_recommendation(
                device_id=device_id,
                reading_id=job["reading_id"],
                recommendation=recommendation,
            )
            print("GROQ AI RECOMMENDATION SUCCESS")
            print(json.dumps(recommendation, indent=2, ensure_ascii=False, default=str))
            print("AI recommendation saved to DynamoDB.")
        except Exception as error:
            print(f"GROQ AI RECOMMENDATION FAILED: {error}")
        finally:
            llm_queue.task_done()

# ---------------------------------------------------------------------------
# MQTT callbacks
# ---------------------------------------------------------------------------
def on_connect(client, userdata, flags, reason_code, properties=None):
    print("\n" + "=" * 60)
    print("CONNECTED TO AWS IOT CORE")
    print("=" * 60)
    print(f"MQTT Client ID : {MQTT_CLIENT_ID}")
    print(f"Sensor Topic   : {SENSOR_TOPIC}")
    if reason_code == 0:
        print("Connection successful.")
        result, _ = client.subscribe(SENSOR_TOPIC, qos=1)
        if result == mqtt.MQTT_ERR_SUCCESS:
            print("Sensor topic subscription SUCCESS")
        else:
            print(f"Sensor topic subscription FAILED: {result}")
    else:
        print(f"MQTT connection failed. Reason code: {reason_code}")


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
    print("\nDisconnected from AWS IoT Core.")
    print(f"Disconnect reason code: {reason_code!r}")
    print(f"Disconnect flags: {disconnect_flags!r}")
    print(f"Client ID: {MQTT_CLIENT_ID}")
    print("=" * 60)


def on_message(client, userdata, message):
    """Validate and store sensor data; enqueue AI work and return promptly."""
    print("\n" + "=" * 60)
    print("NEW SENSOR MESSAGE")
    print("=" * 60)
    print(f"Topic: {message.topic}")

    try:
        payload_string = message.payload.decode("utf-8")
        sensor_data = json.loads(payload_string)
        if not isinstance(sensor_data, dict):
            raise ValueError("Payload must be a JSON object.")

        device_id = sensor_data.get("device_id")
        timestamp = sensor_data.get("timestamp")
        environment = sensor_data.get("environment")
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError("device_id must be a non-empty string.")
        if not isinstance(timestamp, str) or not timestamp.strip():
            raise ValueError("timestamp must be a non-empty string.")
        if not isinstance(environment, dict):
            raise ValueError("environment must be a JSON object.")

        required_fields = ("temperature", "humidity", "soil_moisture", "soil_raw")
        for field in required_fields:
            value = environment.get(field)
            if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Missing or invalid sensor field: {field}")

        temperature = environment["temperature"]
        humidity = environment["humidity"]
        soil_moisture = environment["soil_moisture"]
        soil_raw = environment["soil_raw"]
        print(json.dumps(sensor_data, indent=2, ensure_ascii=False))
        print("\nSensor Information")
        print("-" * 40)
        print(f"Device ID      : {device_id}")
        print(f"Device Time    : {timestamp}")
        print(f"Temperature    : {temperature} °C")
        print(f"Humidity       : {humidity} %")
        print(f"Soil Moisture  : {soil_moisture} %")
        print(f"Soil Raw       : {soil_raw}")

        backend_time = datetime.now(timezone.utc).isoformat()
        weather = get_latest_weather()
        print(f"Backend received at: {backend_time}")
        print(f"Weather snapshot: {'available' if weather is not None else 'not available yet'}")

        # FIXED: pass the thread-safe fetched 'weather' variable instead of undefined 'weather_snapshot'
        care_assessment = assess_plant_care(
            sensor_data,
            weather=weather
        )
        print("\nPLANT-CARE ASSESSMENT")
        print(f"Status: {care_assessment['care_status']}")
        print("Observations:")
        for observation in care_assessment["observations"]:
            print(f"- {observation}")
        print("Recommended actions:")
        for action in care_assessment["recommended_actions"]:
            print(f"- {action}")

        care_topic = f"greenpulse/device/{device_id}/care"
        payload = {
            "device_id": device_id,
            "timestamp": timestamp,
            "care_assessment": care_assessment,
        }

        result = client.publish(
            care_topic,
            json.dumps(payload),
            qos=1,
        )

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"Care assessment queued for MQTT publish: {care_topic}")
        else:
            print(f"Care MQTT publish failed with code: {result.rc}")

        try:
            reading_id = save_sensor_reading(
                device_id=device_id,
                timestamp=timestamp,
                temperature=temperature,
                humidity=humidity,
                soil_moisture=soil_moisture,
                soil_raw=soil_raw,
                backend_time=backend_time,
                mqtt_topic=message.topic,
                weather=weather,
                care_assessment=care_assessment,
            )
            print("\nDYNAMODB WRITE SUCCESS")
            print(f"Table      : {DYNAMODB_TABLE}")
            print(f"Device ID  : {device_id}")
            print(f"Reading ID : {reading_id}")
        except Exception as db_error:
            print(f"DYNAMODB WRITE FAILED: {db_error}")
            return

        queue_ai_recommendation(
            device_id=device_id,
            reading_id=reading_id,
            sensor_data={
                "device_id": device_id,
                "temperature": temperature,
                "humidity": humidity,
                "soil_moisture": soil_moisture,
                "soil_raw": soil_raw,
            },
            weather=weather,
            care_assessment=care_assessment,
        )
        print("=" * 60)

    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        print(f"ERROR: MQTT payload is not valid UTF-8 JSON: {error}")
    except Exception as error:
        print(f"ERROR processing sensor message: {error}")

# ---------------------------------------------------------------------------
# MQTT client, TLS, and startup
# ---------------------------------------------------------------------------
client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=MQTT_CLIENT_ID,
)
client.reconnect_delay_set(min_delay=1, max_delay=30)
client.enable_logger()
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect
client.tls_set(
    ca_certs=CA_FILE,
    certfile=CERT_FILE,
    keyfile=KEY_FILE,
    tls_version=ssl.PROTOCOL_TLS_CLIENT,
)

weather_thread = threading.Thread(
    target=weather_refresh_loop,
    name="GreenPulseWeather",
    daemon=True,
)
weather_thread.start()

if generate_care_recommendation is not None:
    llm_thread = threading.Thread(
        target=llm_worker_loop,
        name="GreenPulseGroqWorker",
        daemon=True,
    )
    llm_thread.start()
else:
    print("LLM integration unavailable; continuing without AI recommendations.")

print("\n" + "=" * 60)
print("GREENPULSE CLOUD BACKEND")
print("=" * 60)
print(f"AWS IoT Endpoint: {AWS_IOT_ENDPOINT}")
print(f"MQTT Port       : {AWS_IOT_PORT}")
print(f"Client ID       : {MQTT_CLIENT_ID}")
print("LLM Provider    : LangChain + Groq (background worker)")
print("Care MQTT Publish: Disabled during connection troubleshooting")
print("\nConnecting to AWS IoT Core...")

try:
    client.connect(AWS_IOT_ENDPOINT, AWS_IOT_PORT, keepalive=60)
except Exception as error:
    print(f"Initial MQTT connection failed: {error!r}")
    raise

# FIXED: Use loop_start() instead of loop_forever() so background network 
# pings and socket management run concurrently in a background thread.
client.loop_start()

print("\nBackend is running...")
print("Waiting for GreenPulse sensor data...")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nShutting down GreenPulse backend...")
    client.loop_stop()
    client.disconnect()