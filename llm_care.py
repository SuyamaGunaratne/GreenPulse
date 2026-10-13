"""GreenPulse AI plant-care recommendations using LangChain + Groq."""
import json
import os
import re

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

load_dotenv()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")


def _create_llm():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing from .env.")

    # Ask Groq to return JSON rather than free-form prose.
    return ChatGroq(
        model=GROQ_MODEL,
        temperature=0.2,
        # GPT-OSS may spend a portion of its completion budget on reasoning.
        # 1200 tokens gives it room to finish a small JSON response reliably.
        max_tokens=1200,
        timeout=45,
        max_retries=1,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def _normalize_sensor_data(sensor_data):
    if not isinstance(sensor_data, dict):
        sensor_data = {}
    readings = sensor_data.get("environment")
    if not isinstance(readings, dict):
        readings = sensor_data.get("sensor_data")
    if not isinstance(readings, dict):
        readings = sensor_data
    return {
        "device_id": sensor_data.get("device_id", readings.get("device_id")),
        "temperature": readings.get("temperature"),
        "humidity": readings.get("humidity"),
        "soil_moisture": readings.get("soil_moisture"),
        "soil_raw": readings.get("soil_raw"),
        "light": readings.get("light"),
        "plant_status": readings.get("plant_status"),
    }


def _response_text(response):
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(parts).strip()
    return str(content).strip() if content else ""


def _parse_json_response(content):
    cleaned = content.strip().lstrip("\ufeff")
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback for responses that wrap JSON in explanatory text.
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            preview = cleaned[:500].replace("\n", " ")
            raise ValueError(
                "Groq response did not contain a JSON object. "
                f"Response preview: {preview!r}"
            )
        try:
            result = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            preview = cleaned[:500].replace("\n", " ")
            raise ValueError(
                "Groq response contained malformed JSON. "
                f"Response preview: {preview!r}"
            ) from exc

    if not isinstance(result, dict):
        raise ValueError("Groq response must be a JSON object.")

    summary = result.get("summary")
    recommendations = result.get("recommendations")
    precautions = result.get("precautions")

    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Groq JSON is missing a non-empty 'summary' string.")
    for field, value in (("recommendations", recommendations), ("precautions", precautions)):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"Groq JSON field '{field}' must be an array of strings.")

    return {
        "summary": summary.strip(),
        "recommendations": [item.strip() for item in recommendations if item.strip()],
        "precautions": [item.strip() for item in precautions if item.strip()],
    }


def care_recommendation(sensor_data, weather=None, assessment=None):
    """Return validated AI advice in the shape expected by the existing backend."""
    context = {
        "sensor_readings": _normalize_sensor_data(sensor_data),
        "weather": weather if isinstance(weather, dict) else {},
        "rule_based_assessment": assessment if isinstance(assessment, dict) else {},
    }

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are GreenPulse's plant-care assistant. Use only the supplied readings, weather and rule-based assessment. Be cautious: never invent data, plant species, diagnoses, or actions performed. A low soil-moisture percentage can indicate dry soil, but tell the user to check the soil physically before watering. Do not recommend watering based only on outdoor weather. Mention missing or uncertain data in precautions. Do not infer air quality from raw sensor values.

Return ONLY one valid JSON object with exactly these keys:
{{"summary":"one short sentence","recommendations":["one concise action"],"precautions":["one concise precaution"]}}
Use 1-2 short recommendations and 1-2 short precautions. No Markdown, no extra keys, and no text outside the JSON."""),
        ("human", "GreenPulse context:\n{context}"),
    ])

    response = (prompt | _create_llm()).invoke({
        "context": json.dumps(context, ensure_ascii=False, indent=2, default=str)
    })
    content = _response_text(response)
    if not content:
        raise RuntimeError("Groq returned an empty care recommendation.")

    result = _parse_json_response(content)
    result["message_type"] = "groq_ai_recommendation"
    return result
