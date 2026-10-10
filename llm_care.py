
import json
import os

from dotenv import load_dotenv
from google import genai


load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing from .env")

client = genai.Client(api_key=GEMINI_API_KEY)


def care_recommendation(
    sensor_data,
    weather=None,
    assessment=None,
):
    """
    Generate plant-care advice from sensor readings,
    weather context, and the rule-based assessment.

    Returns a dictionary containing:
    summary, recommendations, and precautions.
    """

    weather = weather or {}
    assessment = assessment or {}

    context = {
        "sensor_readings": sensor_data,
        "weather": weather,
        "rule_based_assessment": assessment,
    }

    prompt = f"""
You are the plant-care assistant for GreenPulse, an IoT system.

Use the supplied sensor readings, weather data, and rule-based
assessment to provide cautious, practical plant-care guidance.

Requirements:
- Do not assume all plants have identical requirements.
- Treat sensor readings and the rule-based assessment as evidence,
  not as a guaranteed diagnosis.
- Do not recommend watering solely from outdoor weather data.
- If soil appears wet, advise checking drainage and the actual soil
  before adding more water.
- If information is missing, acknowledge the uncertainty.
- Do not invent measurements or claim actions were performed.
- Keep the advice concise and easy to understand.

Return ONLY valid JSON using this exact structure:
{{
  "summary": "A short description of the current situation",
  "recommendations": [
    "Practical action 1",
    "Practical action 2"
  ],
  "precautions": [
    "Important uncertainty or precaution"
  ]
}}

GreenPulse context:
{json.dumps(context, indent=2)}
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
        },
    )

    if not response.text:
        raise ValueError("Gemini returned an empty response.")

    result = json.loads(response.text)

    # Validate the basic response structure before using it.
    if not isinstance(result, dict):
        raise ValueError("Gemini response must be a JSON object.")

    if not isinstance(result.get("summary"), str):
        raise ValueError("Gemini response is missing a valid summary.")

    if not isinstance(result.get("recommendations"), list):
        raise ValueError("Gemini response recommendations must be a list.")

    if not isinstance(result.get("precautions"), list):
        raise ValueError("Gemini response precautions must be a list.")

    return result
