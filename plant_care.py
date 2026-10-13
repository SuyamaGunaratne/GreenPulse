"""
GreenPulse general plant-care assessment.
Thresholds are initial configurable values, not universal plant requirements.
"""
from datetime import datetime, timezone

SOIL_DRY_THRESHOLD = 30
SOIL_WET_THRESHOLD = 70
LOW_TEMPERATURE_THRESHOLD_C = 10
HIGH_TEMPERATURE_THRESHOLD_C = 35
LOW_HUMIDITY_THRESHOLD_PERCENT = 30
HIGH_HUMIDITY_THRESHOLD_PERCENT = 85


def _as_number(value):
    """Convert a finite numeric value or return None for invalid/missing data."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or abs(number) == float("inf"):
        return None
    return number


def assess_plant_care(sensor_data, weather=None):
    """Assess sensor data; supports flat readings or an ESP32 environment object."""
    if not isinstance(sensor_data, dict):
        sensor_data = {}
    weather = weather if isinstance(weather, dict) else {}
    environment = sensor_data.get("environment", sensor_data)
    if not isinstance(environment, dict):
        environment = {}

    soil = _as_number(environment.get("soil_moisture"))
    temperature = _as_number(environment.get("temperature"))
    humidity = _as_number(environment.get("humidity"))
    observations, actions, risks = [], [], []

    if soil is None:
        observations.append("Soil moisture reading is unavailable or invalid.")
        actions.append("Check the soil-moisture sensor connection and calibration.")
    elif not 0 <= soil <= 100:
        observations.append("Soil moisture reading is outside the valid range.")
        actions.append("Check the soil-moisture sensor calibration.")
    elif soil <= SOIL_DRY_THRESHOLD:
        observations.append("The sensor indicates potentially dry soil.")
        actions.append("Check the soil directly before deciding whether to water.")
        risks.append("soil_dry")
    elif soil >= SOIL_WET_THRESHOLD:
        observations.append("The sensor indicates wet soil.")
        actions.append("Check the actual soil and drainage before adding more water.")
        risks.append("soil_wet")
    else:
        observations.append("Soil moisture is within the configured middle range.")

    if temperature is None:
        observations.append("Plant-area temperature is unavailable or invalid.")
    elif temperature >= HIGH_TEMPERATURE_THRESHOLD_C:
        observations.append("Plant-area temperature is high.")
        actions.append("Check whether the plant is exposed to excessive heat.")
        risks.append("high_temperature")
    elif temperature <= LOW_TEMPERATURE_THRESHOLD_C:
        observations.append("Plant-area temperature is low.")
        actions.append("Check whether the plant needs protection from cold conditions.")
        risks.append("low_temperature")
    else:
        observations.append("Plant-area temperature is within the configured range.")

    if humidity is None:
        observations.append("Air humidity reading is unavailable or invalid.")
    elif not 0 <= humidity <= 100:
        observations.append("Air humidity reading is outside the valid range.")
    elif humidity < LOW_HUMIDITY_THRESHOLD_PERCENT:
        observations.append("Air humidity is low.")
        actions.append("Check whether the plant may be affected by dry air.")
        risks.append("low_humidity")
    elif humidity > HIGH_HUMIDITY_THRESHOLD_PERCENT:
        observations.append("Air humidity is high.")
        actions.append("Check airflow and whether the environment stays excessively damp.")
        risks.append("high_humidity")
    else:
        observations.append("Air humidity is within the configured range.")

    outdoor_temp = _as_number(weather.get("temperature_c"))
    precipitation = _as_number(weather.get("precipitation_mm"))
    if outdoor_temp is not None:
        observations.append(f"Reported outdoor temperature is {outdoor_temp:g} °C.")
    if precipitation is not None:
        observations.append(f"Reported precipitation is {precipitation:g} mm.")
        if precipitation > 0:
            actions.append(
                "Consider recent precipitation, but check the actual soil before "
                "changing watering decisions."
            )

    valid_count = sum(value is not None for value in (soil, temperature, humidity))
    if valid_count == 0:
        status = "INSUFFICIENT_DATA"
    elif risks:
        status = "ATTENTION"
    else:
        status = "MONITOR"

    if not actions:
        actions.append("Continue monitoring the plant's conditions.")

    return {
        "assessed_at": datetime.now(timezone.utc).isoformat(),
        "care_status": status,
        "observations": observations,
        "recommended_actions": actions,
        "detected_risks": risks,
        "weather_context_available": bool(weather),
    }
