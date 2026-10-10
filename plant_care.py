
"""
GreenPulse - General Plant-Care Assessment
Uses sensor readings and weather context to identify possible plant-care risks.
"""

from datetime import datetime, timezone

# Initial general-purpose thresholds.
# These are configurable starting points, not universal plant requirements.
SOIL_DRY_THRESHOLD = 30
SOIL_WET_THRESHOLD = 70

LOW_TEMPERATURE_THRESHOLD_C = 10
HIGH_TEMPERATURE_THRESHOLD_C = 35

LOW_HUMIDITY_THRESHOLD_PERCENT = 30
HIGH_HUMIDITY_THRESHOLD_PERCENT = 85


def assess_plant_care(sensor_data, weather=None):
    """
    Args:
        sensor_data: Dictionary containing temperature, humidity,
                     and soil_moisture readings.
        weather: Optional dictionary containing current weather fields.

    Returns:
        A dictionary with care status, observations, and actions.
    """

    weather = weather or {}
    observations = []
    recommended_actions = []
    risks = []

    # Read the sensor values.
    # Supports either a flat dictionary or the ESP32 environment structure.
    environment = sensor_data.get("environment", sensor_data)

    soil_moisture = environment.get("soil_moisture")
    temperature = environment.get("temperature")
    humidity = environment.get("humidity")

    # Soil assessment
    if soil_moisture is None:
        observations.append("Soil moisture reading is unavailable.")
        recommended_actions.append(
            "Check the soil-moisture sensor connection."
        )
    elif not 0 <= soil_moisture <= 100:
        observations.append("Soil moisture reading is outside the valid range.")
        recommended_actions.append(
            "Check the soil-moisture sensor calibration."
        )
    elif soil_moisture <= SOIL_DRY_THRESHOLD:
        observations.append("The sensor indicates potentially dry soil.")
        recommended_actions.append(
            "Check the soil directly before deciding whether to water."
        )
        risks.append("soil_dry")
    elif soil_moisture >= SOIL_WET_THRESHOLD:
        observations.append("The sensor indicates wet soil.")
        recommended_actions.append(
            "Avoid adding water until the soil condition has been checked."
        )
        risks.append("soil_wet")
    else:
        observations.append("Soil moisture is within the configured middle range.")

    # Temperature assessment
    if temperature is None:
        observations.append("Plant-area temperature is unavailable.")
    elif temperature >= HIGH_TEMPERATURE_THRESHOLD_C:
        observations.append("Plant-area temperature is high.")
        recommended_actions.append(
            "Check whether the plant is exposed to excessive heat."
        )
        risks.append("high_temperature")
    elif temperature <= LOW_TEMPERATURE_THRESHOLD_C:
        observations.append("Plant-area temperature is low.")
        recommended_actions.append(
            "Check whether the plant needs protection from cold conditions."
        )
        risks.append("low_temperature")
    else:
        observations.append("Plant-area temperature is within the configured range.")

    # Relative humidity assessment
    if humidity is None:
        observations.append("Air humidity reading is unavailable.")
    elif not 0 <= humidity <= 100:
        observations.append("Air humidity reading is outside the valid range.")
    elif humidity < LOW_HUMIDITY_THRESHOLD_PERCENT:
        observations.append("Air humidity is low.")
        recommended_actions.append(
            "Check whether the plant may be affected by dry air."
        )
        risks.append("low_humidity")
    elif humidity > HIGH_HUMIDITY_THRESHOLD_PERCENT:
        observations.append("Air humidity is high.")
        recommended_actions.append(
            "Check airflow and whether the plant's environment stays excessively damp."
        )
        risks.append("high_humidity")
    else:
        observations.append("Air humidity is within the configured range.")

    # Weather context: use it as supporting information, not as a substitute
    # for checking the plant's actual soil.
    weather_temperature = weather.get("temperature_c")
    precipitation = weather.get("precipitation_mm")

    if weather_temperature is not None:
        observations.append(
            f"Reported outdoor temperature is {weather_temperature} °C."
        )

    if precipitation is not None:
        observations.append(
            f"Reported precipitation is {precipitation} mm."
        )
        if precipitation > 0:
            recommended_actions.append(
                "Consider recent precipitation, but check the actual soil "
                "before changing watering decisions."
            )

    # Determine status from the risks detected.
    if not observations:
        status = "INSUFFICIENT_DATA"
    elif not risks:
        status = "MONITOR"
    elif "high_temperature" in risks or "low_temperature" in risks:
        status = "ATTENTION"
    elif "soil_dry" in risks or "soil_wet" in risks:
        status = "ATTENTION"
    else:
        status = "MONITOR"

    if not recommended_actions:
        recommended_actions.append(
            "Continue monitoring the plant's conditions."
        )

    return {
        "assessed_at": datetime.now(timezone.utc).isoformat(),
        "care_status": status,
        "observations": observations,
        "recommended_actions": recommended_actions,
        "detected_risks": risks,
        "weather_context_available": bool(weather),
    }
