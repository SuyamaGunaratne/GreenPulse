
import os

import boto3
import pandas as pd
import plotly.express as px
import streamlit as st
from boto3.dynamodb.conditions import Key
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh

# --------------------------------------------------
# Configuration
# --------------------------------------------------
load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
AWS_PROFILE = os.getenv("AWS_PROFILE", "greenpulse-local")
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "GreenPluseSensorReadings")
MAX_HISTORY = 100

st.set_page_config(
    page_title="GreenPulse | Plant Health",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------
# Theme mode changer
# --------------------------------------------------
with st.sidebar:
    st.markdown("## 🌿 GreenPulse")

    theme_mode = st.radio(
        "🎨 Appearance",
        ["Light", "Dark"],
        horizontal=True,
        key="gp_theme_mode",
    )

is_dark = theme_mode == "Dark"

# --------------------------------------------------
# Theme variables
# --------------------------------------------------
if is_dark:
    theme_css = """
    :root {
        --forest: #C1E8C4;
        --green: #8FC99A;
        --sage: #759A7B;
        --mint: #233D2C;
        --cream: #18251C;
        --ink: #E5EFE5;
        --muted: #A5B7A6;
        --border: #354A39;
        --surface: #243429;
        --page: #17221A;
        --sidebar: #202F23;
        --hero-start: #153622;
        --hero-end: #326E48;
    }
    """
else:
    theme_css = """
    :root {
        --forest: #214E34;
        --green: #387653;
        --sage: #8DAF91;
        --mint: #E8F3E8;
        --cream: #F7F8F1;
        --ink: #25382B;
        --muted: #758477;
        --border: #E1E9DE;
        --surface: #FFFFFF;
        --page: #F5F8F1;
        --sidebar: #EAF2E7;
        --hero-start: #183F2A;
        --hero-end: #63936A;
    }
    """

# --------------------------------------------------
# Custom styling and animations
# --------------------------------------------------
st.markdown(
    "<style>\n"
    + theme_css
    + """
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap');

    .stApp {
        background:
            radial-gradient(ellipse at 0% 0%, var(--mint), transparent 45%),
            var(--page);
        color: var(--ink);
        font-family: 'DM Sans', sans-serif;
        transition: background 0.3s ease;
    }

    [data-testid="stHeader"] {
        background: transparent;
    }

    [data-testid="stSidebar"] {
        background: var(--sidebar);
        border-right: 1px solid var(--border);
    }

    [data-testid="stSidebar"] * {
        color: var(--ink);
    }

    h1, h2, h3 {
        color: var(--forest) !important;
        font-family: 'Manrope', sans-serif !important;
        letter-spacing: -0.5px;
    }

    h2 {
        font-size: 1.35rem !important;
    }

    p, label, li {
        line-height: 1.65;
    }

    /* Hero banner */
    .hero {
        position: relative;
        overflow: hidden;
        background: linear-gradient(
            120deg,
            var(--hero-start),
            #326E48 68%,
            var(--hero-end)
        );
        color: white;
        padding: 30px 32px;
        border-radius: 24px;
        margin: 6px 0 22px 0;
        box-shadow: 0 12px 32px rgba(36, 83, 52, 0.15);
        animation: enter 0.7s ease-out both;
    }

    .hero h1 {
        color: white !important;
        font-size: clamp(1.8rem, 4vw, 2.65rem) !important;
        margin: 4px 0 8px 0;
        line-height: 1.2;
    }

    .hero p {
        color: #E1F0E0;
        margin: 0;
        font-size: 0.98rem;
    }

    .hero-kicker {
        color: #C9E8C6;
        text-transform: uppercase;
        letter-spacing: 2px;
        font-size: 0.72rem;
        font-weight: 700;
    }

    .hero-plant {
        position: absolute;
        right: 34px;
        top: 12px;
        font-size: clamp(4rem, 9vw, 7rem);
        opacity: 0.23;
        animation: floatPlant 5s ease-in-out infinite;
        pointer-events: none;
    }

    .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 13px;
        background: rgba(255,255,255,0.12);
        border: 1px solid rgba(255,255,255,0.25);
        border-radius: 999px;
        color: #F3FFF0;
        font-size: 0.83rem;
        font-weight: 600;
        margin-top: 17px;
    }

    .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #A6E5A4;
        box-shadow: 0 0 0 4px rgba(166,229,164,0.15);
    }

    /* Sensor metric cards */
    [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 19px;
        padding: 19px 20px;
        min-height: 120px;
        box-shadow: 0 5px 18px rgba(39, 73, 45, 0.06);
        transition: transform 0.22s ease, box-shadow 0.22s ease;
        animation: enter 0.55s ease-out both;
    }

    [data-testid="stMetric"]:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 26px rgba(39, 73, 45, 0.12);
    }

    [data-testid="stMetricLabel"] {
        color: var(--muted) !important;
        font-weight: 600;
        font-size: 0.88rem;
    }

    [data-testid="stMetricValue"] {
        color: var(--forest) !important;
        font-family: 'Manrope', sans-serif;
        font-size: clamp(1.25rem, 2.2vw, 2rem) !important;
        font-weight: 800;
        overflow-wrap: anywhere;
    }

    /* Supporting sections */
    .section-note {
        color: var(--muted);
        font-size: 0.88rem;
        margin-top: -9px;
        margin-bottom: 16px;
    }

    [data-testid="stExpander"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 15px;
    }

    [data-testid="stDataFrame"] {
        border: 1px solid var(--border);
        border-radius: 14px;
        overflow: hidden;
    }

    [data-testid="stPlotlyChart"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 8px;
    }

    [data-testid="stAlert"] {
        border-radius: 13px;
    }

    .footer {
        border-top: 1px solid var(--border);
        margin-top: 28px;
        padding: 18px 0 8px;
        color: var(--muted);
        font-size: 0.82rem;
        text-align: center;
    }

    /* Animations */
    @keyframes enter {
        from {
            opacity: 0;
            transform: translateY(12px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    @keyframes floatPlant {
        0%, 100% {
            transform: translateY(0) rotate(-4deg);
        }
        50% {
            transform: translateY(-9px) rotate(3deg);
        }
    }

    /* Mobile and tablet */
    @media (max-width: 768px) {
        .block-container {
            padding: 1rem 0.85rem 2rem !important;
        }

        .hero {
            padding: 24px 20px;
            border-radius: 19px;
        }

        .hero-plant {
            right: 12px;
            top: 20px;
            font-size: 4rem;
        }

        [data-testid="stMetric"] {
            padding: 13px 12px;
            min-height: 100px;
            border-radius: 15px;
        }

        [data-testid="stMetricLabel"] {
            font-size: 0.78rem;
        }

        [data-testid="stMetricValue"] {
            font-size: 1.2rem !important;
        }

        h2 {
            font-size: 1.2rem !important;
        }
    }

    /* Respect reduced-motion accessibility settings */
    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.01ms !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------
# Dashboard header
# --------------------------------------------------
st.markdown(
    """
    <div class="hero">
        <div class="hero-kicker">Smart indoor gardening</div>
        <h1>GreenPulse 🌿</h1>
        <p>Your plant's environment, at a glance.</p>
        <div class="status-pill">
            <span class="status-dot"></span>
            Live sensor monitoring
        </div>
        <div class="hero-plant">🪴</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Refresh the dashboard every 10 seconds.
st_autorefresh(
    interval=10_000,
    key="greenpulse_dashboard_refresh",
)

# --------------------------------------------------
# Sidebar settings
# --------------------------------------------------
with st.sidebar:
    st.markdown("### 🪴 Your garden")
    st.caption("Monitor the conditions around your indoor plant.")

    device_id = st.text_input(
        "Device ID",
        value="GP001",
        help="Enter the device ID configured in your GreenPulse backend.",
    ).strip()

    st.divider()

    st.markdown("### Connection settings")
    st.caption(f"**AWS Region**\n\n{AWS_REGION}")
    st.caption(f"**DynamoDB table**\n\n{DYNAMODB_TABLE}")

    st.divider()

    st.caption("🔒 Read-only dashboard")
    st.caption(
        "Sensor data refreshes every 10 seconds. "
        "No MQTT messages are published."
    )

# --------------------------------------------------
# DynamoDB connection
# --------------------------------------------------
@st.cache_resource
def get_table():
    session = boto3.Session(
        profile_name=AWS_PROFILE,
        region_name=AWS_REGION,
    )
    return session.resource("dynamodb").Table(DYNAMODB_TABLE)


# --------------------------------------------------
# Utility functions
# --------------------------------------------------
def number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def display_number(value, suffix=""):
    value = number(value)
    return f"{value:.1f}{suffix}" if value is not None else "—"


def list_value(value):
    return value if isinstance(value, list) else []


# --------------------------------------------------
# Read sensor data
# --------------------------------------------------
if not device_id:
    st.warning("Enter a device ID in the sidebar.")
    st.stop()

try:
    response = get_table().query(
        KeyConditionExpression=Key("device_id").eq(device_id),
        ScanIndexForward=False,
        Limit=MAX_HISTORY,
    )
    readings = response.get("Items", [])

except Exception as exc:
    st.error("Unable to retrieve your plant's sensor readings.")
    st.code(str(exc))
    st.info(
        "Check your AWS profile, DynamoDB table name, region, "
        "and DynamoDB Query permissions."
    )
    st.stop()

if not readings:
    st.warning(f"No sensor readings found for device {device_id}.")
    st.info(
        "Confirm that your ESP32 and GreenPulse backend are running "
        "and saving readings to DynamoDB."
    )
    st.stop()

# --------------------------------------------------
# Latest reading and associated data
# --------------------------------------------------
latest = readings[0]

assessment = latest.get("care_assessment") or {}
weather = latest.get("weather") or {}

ai_item = next(
    (
        item
        for item in readings
        if item.get("care_recommendation")
    ),
    None,
)

ai = (ai_item or {}).get("care_recommendation") or {}

reading_time = (
    latest.get("timestamp")
    or latest.get("backend_received_at")
    or "Unknown"
)

status = assessment.get("care_status", "UNKNOWN")

st.caption(
    f"🌿 **Device:** {device_id}  ·  "
    f"**Latest reading:** {reading_time}"
)

# --------------------------------------------------
# Environment overview
# --------------------------------------------------
st.subheader("Your plant's environment")

st.markdown(
    '<p class="section-note">'
    "Current conditions reported by your indoor sensors."
    "</p>",
    unsafe_allow_html=True,
)

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "🌡️ Temperature",
    display_number(latest.get("temperature"), " °C"),
)

c2.metric(
    "💧 Air humidity",
    display_number(latest.get("humidity"), " %"),
)

c3.metric(
    "🌱 Soil moisture",
    display_number(latest.get("soil_moisture"), " %"),
)

c4.metric(
    "🪴 Plant-care status",
    str(status),
)

if latest.get("soil_raw") is not None:
    st.caption(
        f"Soil sensor raw value: {latest.get('soil_raw')}"
    )

if (
    number(latest.get("soil_moisture")) == 0
    and number(latest.get("soil_raw")) == 4095
):
    st.warning(
        "⚠️ Soil moisture is 0% and the raw value is 4095. "
        "Check the sensor wiring and calibration before relying "
        "on watering decisions."
    )

# --------------------------------------------------
# Plant-care assessment and Groq AI
# --------------------------------------------------
left, right = st.columns(2, gap="large")

with left:
    st.subheader("🌿 Plant-care assessment")

    if assessment:
        observations = list_value(
            assessment.get("observations")
        )
        actions = list_value(
            assessment.get("recommended_actions")
        )
        risks = list_value(
            assessment.get("detected_risks")
        )

        if observations:
            st.markdown("**What we observe**")
            for value in observations:
                st.markdown(f"- {value}")

        if actions:
            st.markdown("**Recommended actions**")
            for value in actions:
                st.markdown(f"- {value}")

        if risks:
            st.markdown("**Detected risks**")
            for value in risks:
                st.markdown(f"- ⚠️ `{value}`")

        if not (observations or actions or risks):
            st.info(
                "The assessment is available, but contains no details."
            )

    else:
        st.info(
            "No plant-care assessment is attached to the latest reading."
        )

with right:
    st.subheader("✨ Groq AI recommendation")

    if ai:
        if ai.get("summary"):
            st.write(ai["summary"])

        recommendations = list_value(
            ai.get("recommendations")
        )
        precautions = list_value(
            ai.get("precautions")
        )

        if recommendations:
            st.markdown("**Suggested care**")
            for value in recommendations:
                st.markdown(f"- {value}")

        if precautions:
            st.markdown("**Precautions**")
            for value in precautions:
                st.markdown(f"- {value}")

        generated_at = (
            ai.get("generated_at")
            or (ai_item or {}).get(
                "care_recommendation_generated_at"
            )
            or "Unknown"
        )

        st.caption(f"Generated at: {generated_at}")

    else:
        st.info(
            f"No AI recommendation was found in the latest "
            f"{len(readings)} readings. "
            "The backend AI cooldown may be active."
        )

# --------------------------------------------------
# Outdoor weather
# --------------------------------------------------
st.subheader("☀️ Outdoor weather")

st.markdown(
    '<p class="section-note">'
    "External weather conditions, when available."
    "</p>",
    unsafe_allow_html=True,
)

if weather:
    w1, w2, w3 = st.columns(3)

    w1.metric(
        "Outdoor temperature",
        display_number(
            weather.get("temperature_c"),
            " °C",
        ),
    )

    w2.metric(
        "Outdoor humidity",
        display_number(
            weather.get("humidity_percent"),
            " %",
        ),
    )

    rain = weather.get(
        "precipitation_mm",
        weather.get("precipitation"),
    )

    w3.metric(
        "Precipitation",
        display_number(rain, " mm"),
    )

else:
    st.info(
        "Weather data is not attached to the latest reading."
    )

# --------------------------------------------------
# Prepare sensor history
# --------------------------------------------------
st.subheader("📈 Sensor history")

st.markdown(
    '<p class="section-note">'
    "Explore changes in your plant's indoor environment over time."
    "</p>",
    unsafe_allow_html=True,
)

rows = []

for item in reversed(readings):
    rows.append(
        {
            "Timestamp": (
                item.get("timestamp")
                or item.get("backend_received_at")
                or ""
            ),
            "Temperature (°C)": number(
                item.get("temperature")
            ),
            "Humidity (%)": number(
                item.get("humidity")
            ),
            "Soil moisture (%)": number(
                item.get("soil_moisture")
            ),
        }
    )

history = pd.DataFrame(rows)

if not history.empty:
    history["Timestamp"] = pd.to_datetime(
        history["Timestamp"],
        errors="coerce",
        utc=True,
    )

    history = history.dropna(
        subset=["Timestamp"]
    )

    chart_columns = [
        col
        for col in [
            "Temperature (°C)",
            "Humidity (%)",
            "Soil moisture (%)",
        ]
        if history[col].notna().any()
    ]

    if chart_columns:
        # Allow users to select which sensor measurements to view.
        selected_sensors = st.multiselect(
            "Select measurements",
            options=chart_columns,
            default=chart_columns,
            key="gp_history_sensors",
        )

        if selected_sensors:
            chart_data = (
                history[["Timestamp"] + selected_sensors]
                .sort_values("Timestamp")
            )

            # Interactive area chart
            fig = px.area(
                chart_data,
                x="Timestamp",
                y=selected_sensors,
                template=(
                    "plotly_dark"
                    if is_dark
                    else "plotly_white"
                ),
                labels={
                    "Timestamp": "Reading time",
                    "value": "Measurement",
                    "variable": "Sensor",
                },
                color_discrete_map={
                    "Temperature (°C)": "#E6B66A",
                    "Humidity (%)": "#70B7D6",
                    "Soil moisture (%)": "#76B985",
                },
            )

            fig.update_layout(
                title="Indoor environment trends",
                height=390,
                margin=dict(
                    l=12,
                    r=12,
                    t=65,
                    b=12,
                ),
                hovermode="x unified",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(
                    family="DM Sans, sans-serif",
                    color=(
                        "#E5EFE5"
                        if is_dark
                        else "#25382B"
                    ),
                ),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="left",
                    x=0,
                ),
            )

            fig.update_xaxes(
                showgrid=False,
                title=None,
            )

            fig.update_yaxes(
                gridcolor=(
                    "#354A39"
                    if is_dark
                    else "#E1E9DE"
                ),
                zeroline=False,
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "responsive": True,
                    "displaylogo": False,
                    "scrollZoom": True,
                },
            )

            st.caption(
                "Hover over the chart for readings. "
                "Use the legend to show or hide sensors, "
                "or zoom in to inspect a time range."
            )

        else:
            st.info(
                "Select at least one sensor measurement to display the chart."
            )

    else:
        st.info(
            "No numeric sensor history is available."
        )

# --------------------------------------------------
# Recent readings table
# --------------------------------------------------
with st.expander("🗂️ View recent saved readings"):
    st.dataframe(
        pd.DataFrame(rows[::-1]),
        use_container_width=True,
        hide_index=True,
    )

# --------------------------------------------------
# Footer
# --------------------------------------------------
st.markdown(
    """
    <div class="footer">
        🌿 <b>GreenPulse</b> · Growing healthier plants through smart monitoring
        <br>
        Read-only dashboard · Powered by ESP32, AWS DynamoDB and AI insights
    </div>
    """,
    unsafe_allow_html=True,
)
