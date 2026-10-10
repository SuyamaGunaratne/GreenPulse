import os
import json
import ssl
import time
import uuid
import threading
from decimal import Decimal
from datetime import datetime, timezone
import boto3
import requests
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from plant_care import assess_plant_care

# Optional LLM integration: a missing key/package must not stop sensor ingestion.
try:
    from llm_care import care_recommendation as generate_care_recommendation
    LLM_IMPORT_ERROR = None
except Exception as import_error:
    generate_care_recommendation = None
    LLM_IMPORT_ERROR = import_error

# =====================================================
# Load environment variables

# =====================================================
load_dotenv()
# AWS IoT Core configuration
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
# DynamoDB configuration
AWS_REGION = os.getenv(
    "AWS_REGION",
    "ap-southeast-1"
)
DYNAMODB_TABLE = os.getenv(
    "DYNAMODB_TABLE",
    "GreenPluseSensorReadings"
)
AWS_PROFILE = os.getenv(
    "AWS_PROFILE",
    "greenpulse-local"
)
# Open-Meteo configuration
WEATHER_API_URL = os.getenv(
    "WEATHER_API_URL",
    "https://api.open-meteo.com/v1/forecast"
)
WEATHER_LATITUDE = float(
    os.getenv("WEATHER_LATITUDE", "6.9271")
)
WEATHER_LONGITUDE = float(
    os.getenv("WEATHER_LONGITUDE", "79.8612")
)
WEATHER_TIMEZONE = os.getenv(
    "WEATHER_TIMEZONE",
    "Asia/Colombo"
)
WEATHER_TEMPERATURE_UNIT = os.getenv(
    "WEATHER_TEMPERATURE_UNIT",
    "celsius"
)
WEATHER_REFRESH_SECONDS = 15 * 60
# Limit Gemini calls so a 5-second sensor interval does not consume API quota.
LLM_COOLDOWN_SECONDS = int(os.getenv("LLM_COOLDOWN_SECONDS", "900"))
CARE_TOPIC_PREFIX = os.getenv("CARE_TOPIC_PREFIX", "greenpulse/device")
last_llm_call_by_device = {}
llm_cooldown_lock = threading.Lock()

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
# Initialize DynamoDB

# =====================================================
print("Initializing DynamoDB connection...")
aws_session = boto3.Session(
    profile_name=AWS_PROFILE,
    region_name=AWS_REGION
)
dynamodb = aws_session.resource("dynamodb")
sensor_table = dynamodb.Table(DYNAMODB_TABLE)
print(f"DynamoDB Region : {AWS_REGION}")
print(f"DynamoDB Table  : {DYNAMODB_TABLE}")
print(f"AWS Profile     : {AWS_PROFILE}")

# =====================================================
# Weather cache

# =====================================================
weather_lock = threading.Lock()
latest_weather = None

# =====================================================
# Fetch current weather from Open-Meteo

# =====================================================

def fetch_weather():
    """Fetch and validate current weather conditions."""
    params = {
        "latitude": WEATHER_LATITUDE,
        "longitude": WEATHER_LONGITUDE,
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "apparent_temperature,"
            "precipitation,"
            "weather_code,"
            "wind_speed_10m"
        ),
        "temperature_unit": WEATHER_TEMPERATURE_UNIT,
        "timezone": WEATHER_TIMEZONE
    }
    response = requests.get(
        WEATHER_API_URL,
        params=params,
        timeout=10
    )
    response.raise_for_status()
    data = response.json()
    current = data.get("current")
    if not isinstance(current, dict):
        raise ValueError(
            "Weather response has no current data."
        )
    required_fields = [
        "time",
        "temperature_2m",
        "relative_humidity_2m",
        "apparent_temperature",
        "precipitation",
        "weather_code",
        "wind_speed_10m"
    ]
    for field in required_fields:
        if current.get(field) is None:
            raise ValueError(
                f"Missing weather field: {field}"
            )
    # Record when our backend fetched the response.
    fetched_at = datetime.now(
        timezone.utc
    ).isoformat()
    return {
        "weather_time": current["time"],
        "fetched_at": fetched_at,
        "temperature_c": current["temperature_2m"],
        "humidity_percent": current["relative_humidity_2m"],
        "apparent_temperature_c": current["apparent_temperature"],
        "precipitation_mm": current["precipitation"],
        "weather_code": current["weather_code"],
        "wind_speed_kmh": current["wind_speed_10m"],
        "latitude": WEATHER_LATITUDE,
        "longitude": WEATHER_LONGITUDE,
        "timezone": WEATHER_TIMEZONE
    }

# =====================================================
# Background weather refresh

# =====================================================

def weather_refresh_loop():
    """Refresh weather without blocking MQTT processing."""
    global latest_weather
    while True:
        try:
            new_weather = fetch_weather()
            # Update the cache only after a successful fetch.
            with weather_lock:
                latest_weather = new_weather
            print()
            print("=" * 60)
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
            print()
            print(f"WEATHER REFRESH FAILED: {error}")
            print("Sensor processing will continue.")
        # Wait before the next request.
        time.sleep(WEATHER_REFRESH_SECONDS)

def get_latest_weather():
    """Return a copy of the latest successful weather snapshot."""
    with weather_lock:
        if latest_weather is None:
            return None
        return dict(latest_weather)

# =====================================================
# Save sensor reading to DynamoDB

# =====================================================

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
    care_recommendation=None
):
    """Store one sensor reading and its optional weather and care results."""
    # Unique sort key prevents consecutive readings from overwriting.
    reading_id = (
        datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
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
        "soil_raw": Decimal(str(soil_raw))
    }
    # Store weather as a nested DynamoDB map when available.
    if weather is not None:
        item["weather"] = {
            key: (
                Decimal(str(value))
                if isinstance(value, (int, float))
                and not isinstance(value, bool)
                else value
            )
            for key, value in weather.items()
        }
    if care_assessment is not None:
        item["care_assessment"] = care_assessment
    if care_recommendation is not None:
        item["care_recommendation"] = care_recommendation
    sensor_table.put_item(Item=item)
    return reading_id

# =====================================================
# MQTT Connected Callback
# =====================================================

def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties=None
):
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
    print(f"Disconnect reason: {reason_code}")

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
        # Decode MQTT payload.
        payload_string = message.payload.decode("utf-8")
        print()
        print("Raw payload:")
        print(payload_string)
        # Parse JSON.
        sensor_data = json.loads(payload_string)
        if not isinstance(sensor_data, dict):
            raise ValueError(
                "Payload must be a JSON object."
            )
        print()
        print("Parsed sensor data:")
        print(json.dumps(sensor_data, indent=2))
        # -------------------------------------------------
        # Extract and validate device information
        # -------------------------------------------------
        device_id = sensor_data.get("device_id")
        timestamp = sensor_data.get("timestamp")
        environment = sensor_data.get("environment")
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError(
                "device_id must be a non-empty string."
            )
        if not isinstance(timestamp, str) or not timestamp.strip():
            raise ValueError(
                "timestamp must be a non-empty string."
            )
        if not isinstance(environment, dict):
            raise ValueError(
                "environment must be a JSON object."
            )
        required_fields = [
            "temperature",
            "humidity",
            "soil_moisture",
            "soil_raw"
        ]
        for field in required_fields:
            value = environment.get(field)
            if value is None or isinstance(value, bool):
                raise ValueError(
                    f"Missing or invalid sensor field: {field}"
                )
            if not isinstance(value, (int, float)):
                raise ValueError(
                    f"Sensor field {field} must be numeric."
                )
        temperature = environment["temperature"]
        humidity = environment["humidity"]
        soil_moisture = environment["soil_moisture"]
        soil_raw = environment["soil_raw"]
        # -------------------------------------------------
        # Display sensor information
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
        print(f"Backend received at: {backend_time}")
        # -------------------------------------------------
        # Get cached weather
        # -------------------------------------------------
        weather = get_latest_weather()
        if weather is not None:
            print("Weather snapshot: available")
            print(
                f"Outdoor temperature: "
                f"{weather['temperature_c']} °C"
            )
            print(
                f"Outdoor humidity: "
                f"{weather['humidity_percent']} %"
            )
        else:
            print(
                "Weather snapshot: not available yet"
            )
        # -------------------------------------------------
        # Assess plant-care conditions using live sensor data
        # and the latest available weather snapshot.
        # -------------------------------------------------
        care_assessment = assess_plant_care(
            {
                "temperature": temperature,
                "humidity": humidity,
                "soil_moisture": soil_moisture,
            },
            weather,
        )
        print()
        print("PLANT-CARE ASSESSMENT")
        print(f"Status: {care_assessment['care_status']}")
        print("Observations:")
        for observation in care_assessment["observations"]:
            print(f"- {observation}")
        print("Recommended actions:")
        for action in care_assessment["recommended_actions"]:
            print(f"- {action}")
        # -------------------------------------------------
        # Optional Gemini LLM recommendation
        # -------------------------------------------------
        # Run only for readings needing attention, with a per-device cooldown.
        care_recommendation = None
        risks = care_assessment.get("detected_risks", [])
        needs_attention = (
            care_assessment.get("care_status") == "ATTENTION" or bool(risks)
        )
        now_monotonic = time.monotonic()
        with llm_cooldown_lock:
            last_llm_call = last_llm_call_by_device.get(device_id, 0)
            llm_allowed = (
                needs_attention
                and now_monotonic - last_llm_call >= LLM_COOLDOWN_SECONDS
            )
        if llm_allowed:
            if generate_care_recommendation is None:
                print("LLM skipped: llm_care could not be loaded.")
                if LLM_IMPORT_ERROR:
                    print(f"LLM setup error: {LLM_IMPORT_ERROR}")
            else:
                try:
                    print("Requesting an AI care recommendation from Gemini...")
                    llm_sensor_data = {
                        "device_id": device_id,
                        "temperature": temperature,
                        "humidity": humidity,
                        "soil_moisture": soil_moisture,
                        "soil_raw": soil_raw,
                    }
                    care_recommendation = generate_care_recommendation(
                        sensor_data=llm_sensor_data,
                        weather=weather,
                        assessment=care_assessment,
                    )
                    # Start the cooldown only after Gemini returns successfully.
                    with llm_cooldown_lock:
                        last_llm_call_by_device[device_id] = time.monotonic()
                    care_recommendation["generated_at"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                    print("GEMINI CARE RECOMMENDATION")
                    print(json.dumps(care_recommendation, indent=2))
                    care_topic = f"{CARE_TOPIC_PREFIX}/{device_id}/care"
                    publish_info = client.publish(
                        care_topic,
                        json.dumps(care_recommendation),
                        qos=1,
                        retain=False,
                    )
                    if publish_info.rc == mqtt.MQTT_ERR_SUCCESS:
                        print(f"Care recommendation queued for MQTT topic: {care_topic}")
                    else:
                        print(f"CARE MQTT PUBLISH FAILED: return code {publish_info.rc}")
                except Exception as llm_error:
                    # LLM failures must not prevent sensor readings being saved.
                    print(f"LLM recommendation failed: {llm_error}")
                    care_recommendation = None
        elif needs_attention:
            print(
                "LLM recommendation skipped: cooldown active "
                f"({LLM_COOLDOWN_SECONDS} seconds per device)."
            )
        # -------------------------------------------------
        # Store sensor data, weather and available care results in DynamoDB
        # -------------------------------------------------
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
                care_recommendation=care_recommendation
            )
            print()
            print("DYNAMODB WRITE SUCCESS")
            print(f"Table      : {DYNAMODB_TABLE}")
            print(f"Device ID  : {device_id}")
            print(f"Reading ID : {reading_id}")
        except Exception as db_error:
            print()
            print("DYNAMODB WRITE FAILED")
            print(f"Error: {db_error}")
        print("=" * 60)
    except (json.JSONDecodeError, UnicodeDecodeError):
        print("ERROR: MQTT payload is not valid UTF-8 JSON.")
    except Exception as error:
        print(f"ERROR processing sensor message: {error}")

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
# Start background weather refresh

# =====================================================
weather_thread = threading.Thread(
    target=weather_refresh_loop,
    name="GreenPulseWeather",
    daemon=True
)
weather_thread.start()

# =====================================================
# Connect to AWS IoT Core

# =====================================================
print()
print("=" * 60)
print("GREENPULSE CLOUD BACKEND")
print("=" * 60)
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
