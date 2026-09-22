import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path

import folium
import requests
import streamlit as st

from streamlit_folium import st_folium
from dotenv import load_dotenv

from dispatch.email_dispatch import send_email, dispatch_advisory
from dispatch.mock_inbox import (
    add_to_inbox,
    get_latest
)


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

MOCK_ADVISORY = (
    BASE_DIR /
    "mock" /
    "advisory.json"
)

MOCK_TRACK = (
    BASE_DIR /
    "mock" /
    "track.geojson"
)

RISK_IMAGE = (
    BASE_DIR /
    "assets" /
    "risk_map.png"
)

BACKTEST_IMAGE = (
    BASE_DIR /
    "assets" /
    "backtest_comparison.png"
)

ADVISORY_API_URL = os.getenv(
    "ADVISORY_API_URL",
    "http://localhost:8000/advisory"
)

FORECAST_API_URL = os.getenv(
    "FORECAST_API_URL",
    "http://localhost:8000/forecast"
)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Coastal Risk Advisor",
    page_icon="🌊",
    layout="wide"
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>

    .main-title {
        font-size: 42px;
        font-weight: 800;
        margin-bottom: 5px;
    }

    .subtitle {
        font-size: 18px;
        color: #666;
        margin-bottom: 30px;
    }

    .risk-high {
        padding: 12px;
        border-radius: 10px;
        background-color: #ffe5e5;
        border: 1px solid #ff7777;
        color: #a00000;
        font-weight: bold;
    }

    .risk-low {
        padding: 12px;
        border-radius: 10px;
        background-color: #e5ffe9;
        border: 1px solid #70c980;
        color: #126b22;
        font-weight: bold;
    }

    .inbox {
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #ddd;
        background-color: #fafafa;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="main-title">🌊 Coastal Risk Advisor</div>',
    unsafe_allow_html=True
)

st.markdown(
    """
    <div class="subtitle">
    Cyclone Impact & Infrastructure Vulnerability Forecaster
    </div>
    """,
    unsafe_allow_html=True
)


st.info(
    "Demo mode: using mock cyclone and advisory data until "
    "the real /forecast and /advisory endpoints are available."
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("⚙️ Demo Controls")

use_real_api = st.sidebar.checkbox(
    "Use real API",
    value=False
)

st.sidebar.markdown("---")

st.sidebar.markdown(
    """
    ### System Status

    🟢 UI: Ready

    🟢 Mock Data: Ready

    🟡 Forecast API: Waiting

    🟡 Advisory API: Waiting

    🟢 Dispatch: Configured
    """
)


# ============================================================
# DATA FUNCTIONS
# ============================================================

def load_mock_advisory():

    with open(
        MOCK_ADVISORY,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def load_mock_track():

    with open(
        MOCK_TRACK,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def fetch_real_advisory():

    response = requests.get(
        ADVISORY_API_URL,
        timeout=8
    )

    response.raise_for_status()

    return response.json()


def fetch_real_forecast():

    response = requests.get(
        FORECAST_API_URL,
        timeout=8
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# TRACK MAP
# ============================================================

def create_track_map(track_data):

    map_center = [
        13.05,
        80.15
    ]

    fmap = folium.Map(
        location=map_center,
        zoom_start=9,
        tiles="OpenStreetMap"
    )

    coordinates = []

    for feature in track_data.get(
        "features",
        []
    ):

        lon, lat = feature[
            "geometry"
        ]["coordinates"]

        coordinates.append(
            [lat, lon]
        )

        properties = feature.get(
            "properties",
            {}
        )

        popup_text = f"""
        <b>Cyclone Track Point</b><br>
        Time: {properties.get("time", "N/A")}<br>
        Wind: {properties.get("wind_kmh", "N/A")} km/h<br>
        Pressure: {properties.get("pressure_hpa", "N/A")} hPa
        """

        folium.CircleMarker(
            location=[lat, lon],
            radius=7,
            popup=popup_text,
            tooltip="Cyclone position",
            fill=True
        ).add_to(fmap)

    if coordinates:

        folium.PolyLine(
            coordinates,
            weight=4
        ).add_to(fmap)

    return fmap


# ============================================================
# LOAD DATA
# ============================================================

try:

    if use_real_api:

        advisory_data = fetch_real_advisory()

        forecast_data = fetch_real_forecast()

    else:

        advisory_data = load_mock_advisory()

        forecast_data = load_mock_track()

except Exception as error:

    st.error(
        f"API/data loading failed: {error}"
    )

    st.warning(
        "Falling back to mock data."
    )

    advisory_data = load_mock_advisory()

    forecast_data = load_mock_track()


# ============================================================
# CYCLONE TRACK
# ============================================================

st.subheader("🌀 Cyclone Track")

track_map = create_track_map(
    forecast_data
)

st_folium(
    track_map,
    width=None,
    height=500
)


# ============================================================
# RISK MAP
# ============================================================

st.subheader("⚠️ Risk Assessment")

col1, col2 = st.columns(
    [2, 1]
)

with col1:

    if RISK_IMAGE.exists():

        st.image(
            RISK_IMAGE,
            caption=(
                "Heuristic Risk Model — "
                "Not a certified forecast"
            ),
            use_container_width=True
        )

    else:

        st.warning(
            "risk_map.png not found."
        )


with col2:

    risk_level = advisory_data.get(
        "risk_level",
        "unknown"
    ).upper()

    st.metric(
        "Current Risk Level",
        risk_level
    )

    st.markdown(
        "### Affected Zones"
    )

    for zone in advisory_data.get(
        "zones",
        []
    ):

        st.write(
            f"📍 {zone}"
        )

    st.warning(
        advisory_data.get(
            "confidence_note",
            "Heuristic model."
        )
    )


# ============================================================
# INFRASTRUCTURE EXPOSURE
# ============================================================

st.subheader("🏗️ Infrastructure Exposure")

c1, c2, c3 = st.columns(3)

with c1:

    st.metric(
        "Substations at Risk",
        "20%"
    )

with c2:

    st.metric(
        "Roads at Risk",
        "12.4 km"
    )

with c3:

    st.metric(
        "Shelters at Risk",
        "7"
    )


# ============================================================
# BACKTEST
# ============================================================

st.subheader(
    "🛰️ Cyclone Michaung Backtest"
)

st.caption(
    "Predicted risk compared with satellite-derived "
    "flood extent. Static backtest for demonstration."
)

if BACKTEST_IMAGE.exists():

    st.image(
        BACKTEST_IMAGE,
        caption="Predicted vs SAR Flood Extent",
        use_container_width=True
    )

else:

    st.warning(
        "backtest_comparison.png not found."
    )


# ============================================================
# DISPATCH FUNCTION
# ============================================================

def dispatch_advisory(advisory_json, timeout=8):
    """
    Dispatch advisory if risk level is HIGH with an 8-second timeout and fallback mechanism.
    """
    risk_level = str(advisory_json.get("risk_level", "")).strip().lower()
    if risk_level != "high":
        return {
            "success": False,
            "status": "not_dispatched",
            "message": "Risk level is not high."
        }

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(send_email, advisory_json)
            result = future.result(timeout=timeout)

        return {
            "success": result.get("success", False),
            "status": "dispatched",
            "message": "Email dispatched successfully."
        }

    except FutureTimeoutError:
        return {
            "success": False,
            "status": "fallback",
            "message": f"Dispatch timed out after {timeout} seconds."
        }

    except Exception as e:
        return {
            "success": False,
            "status": "fallback",
            "message": f"Dispatch failed: {e}"
        }


# ============================================================
# ADVISORY
# ============================================================

st.divider()

st.subheader(
    "🚨 Advisory Generation & Dispatch"
)

st.write(
    "Generate the bilingual advisory and dispatch it "
    "when the risk level is HIGH."
)


if st.button(
    "🚨 Generate & Dispatch Advisory",
    type="primary",
    use_container_width=True
):

    with st.spinner(
        "Generating and dispatching advisory..."
    ):

        try:

            # ------------------------------------------------
            # Get advisory
            # ------------------------------------------------

            if use_real_api:

                advisory_data = fetch_real_advisory()

            else:

                advisory_data = load_mock_advisory()

            # ------------------------------------------------
            # Dispatch advisory with timeout + fallback
            # ------------------------------------------------

            result = dispatch_advisory(advisory_data)

            if result["status"] == "not_dispatched":

                st.info(
                    "Risk level is not HIGH. "
                    "Emergency dispatch was not triggered."
                )

                add_to_inbox(
                    advisory_data,
                    "Not dispatched — risk is not high"
                )

            elif result["status"] == "dispatched":

                add_to_inbox(
                    advisory_data,
                    "Email dispatched successfully"
                )

                st.success(
                    "✓ Advisory dispatched successfully!"
                )

            else:

                add_to_inbox(
                    advisory_data,
                    "Demo fallback — "
                    "advisory displayed locally"
                )

                st.warning(
                    "⚠️ External dispatch failed. "
                    "Using demo inbox fallback."
                )

                st.caption(
                    result["message"]
                )

        except Exception as error:

            st.error(
                f"Advisory process failed: {error}"
            )


# ============================================================
# LATEST MUNICIPAL INBOX
# ============================================================

st.divider()

st.subheader(
    "🏛️ Municipal Authority Inbox"
)

latest = get_latest()

if latest:

    risk = latest["risk_level"].upper()

    if risk == "HIGH":

        st.markdown(
            f"""
            <div class="risk-high">
            🚨 HIGH RISK ADVISORY RECEIVED
            </div>
            """,
            unsafe_allow_html=True
        )

    else:

        st.markdown(
            f"""
            <div class="risk-low">
            ✓ {risk} RISK
            </div>
            """,
            unsafe_allow_html=True
        )

    st.write(
        f"**Received:** {latest['timestamp']}"
    )

    st.write(
        f"**Dispatch Status:** "
        f"{latest['dispatch_status']}"
    )

    st.markdown(
        "### 📍 Affected Zones"
    )

    for zone in latest["zones"]:

        st.write(
            f"• {zone}"
        )

    st.markdown(
        "### 🇬🇧 English Advisory"
    )

    st.info(
        latest["advisory_en"]
    )

    st.markdown(
        "### 🇮🇳 Tamil Advisory"
    )

    st.info(
        latest["advisory_ta"]
    )

    st.markdown(
        "### ℹ️ Confidence Note"
    )

    st.caption(
        latest["confidence_note"]
    )

else:

    st.info(
        "No advisory has been dispatched yet. "
        "Click the Generate & Dispatch button."
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Coastal Risk Advisor | "
    "Heuristic risk model — not a certified forecast | "
    "Demo system"
)
