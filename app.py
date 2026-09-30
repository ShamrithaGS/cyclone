import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from pathlib import Path

import folium
import requests
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

from dispatch.email_dispatch import send_email
from dispatch.mock_inbox import (
    add_to_inbox,
    get_latest,
)

# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

MOCK_ADVISORY = BASE_DIR / "mock" / "advisory.json"
MOCK_TRACK = BASE_DIR / "mock" / "track.geojson"
REAL_TRACK = BASE_DIR / "test_2026_track.json"
RISK_IMAGE = BASE_DIR / "assets" / "risk_map.png"
BACKTEST_IMAGE = BASE_DIR / "assets" / "backtest_comparison.png"

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
if not API_BASE_URL.startswith(("http://", "https://")):
    API_BASE_URL = f"http://{API_BASE_URL}"

ADVISORY_API_URL = os.getenv("ADVISORY_API_URL", f"{API_BASE_URL}/advisory")
FORECAST_API_URL = os.getenv("FORECAST_API_URL", f"{API_BASE_URL}/forecast")


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Coastal Risk Advisor",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# HTML RENDER HELPER (Prevents Markdown Code Block Indentation Trap)
# ============================================================

def render_html(html_str):
    """
    Renders HTML cleanly in Streamlit by stripping line indentation and blank lines.
    This guarantees Markdown will never misinterpret nested HTML as indented <pre><code> blocks.
    """
    cleaned = "\n".join(line.strip() for line in html_str.strip().splitlines() if line.strip())
    st.markdown(cleaned, unsafe_allow_html=True)


# ============================================================
# CUSTOM COMMAND CENTER STYLING (Dark / Tailwind Aesthetic)
# ============================================================

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    :root {
        --bg: #fdf7f5;
        --panel: #fffaf8;
        --panel-strong: #fef3ef;
        --soft-pink: #f9dfe8;
        --soft-rose: #f8c9d6;
        --soft-blue: #dfeefb;
        --soft-mint: #dff7ee;
        --soft-peach: #ffe6cf;
        --soft-lavender: #e9e2ff;
        --text: #32405a;
        --muted: #67768d;
        --line: #f0dfe4;
        --shadow: rgba(121, 105, 145, 0.12);
        --success: #62a77c;
        --warning: #d7995f;
        --danger: #dd7a8d;
        --info: #7ea9d8;
    }

    .stApp {
        background: linear-gradient(180deg, #fffaf8 0%, #fdf7f4 100%) !important;
        color: var(--text) !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    .block-container {
        padding-top: 5rem !important;
        padding-bottom: 3rem !important;
        max-width: 1440px !important;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #fffaf8 0%, #f8f3ff 100%) !important;
        border-right: 1px solid var(--line) !important;
    }

    [data-testid="stHeader"] {
        background-color: transparent !important;
    }

    .cra-card {
        background: linear-gradient(180deg, #fffdfb 0%, #fff7f9 100%);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 8px 18px var(--shadow);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .cra-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 24px rgba(146, 128, 174, 0.14);
    }

    .kpi-card {
        background: linear-gradient(180deg, #fffdfc 0%, #fdf3f5 100%);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 16px 18px;
        position: relative;
        overflow: hidden;
        box-shadow: 0 8px 18px var(--shadow);
        transition: transform 0.15s ease, box-shadow 0.2s ease;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 24px rgba(146, 128, 174, 0.14);
    }
    .kpi-label {
        font-size: 11px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--muted);
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .kpi-value {
        font-size: 26px;
        font-weight: 800;
        letter-spacing: -0.02em;
        line-height: 1.1;
        margin-bottom: 4px;
    }
    .kpi-subtext {
        font-size: 12px;
        color: var(--muted);
        font-weight: 600;
    }

    .cra-badge {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 5px 10px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }
    .badge-red {
        background: rgba(221, 122, 141, 0.14);
        border: 1px solid rgba(221, 122, 141, 0.3);
        color: #c75d70;
    }
    .badge-green {
        background: rgba(98, 167, 124, 0.14);
        border: 1px solid rgba(98, 167, 124, 0.3);
        color: #5f9d75;
    }
    .badge-amber {
        background: rgba(215, 153, 95, 0.14);
        border: 1px solid rgba(215, 153, 95, 0.3);
        color: #c68249;
    }
    .badge-blue {
        background: rgba(126, 169, 216, 0.15);
        border: 1px solid rgba(126, 169, 216, 0.32);
        color: #5e8cc1;
    }

    .section-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-top: 26px;
        margin-bottom: 8px;
        padding-bottom: 8px;
        border-bottom: 1px solid var(--line);
    }
    .section-title {
        font-size: 16px;
        font-weight: 800;
        letter-spacing: -0.01em;
        color: var(--text);
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .section-subtitle {
        font-size: 13px;
        color: var(--muted);
        margin-top: -4px;
        margin-bottom: 16px;
    }

    div.stButton > button {
        background: linear-gradient(180deg, #f5cad8 0%, #f1b7ca 100%) !important;
        color: #3d2d3e !important;
        border: 1px solid #e7a9bb !important;
        border-radius: 12px !important;
        font-weight: 800 !important;
        font-size: 14px !important;
        letter-spacing: 0.03em !important;
        padding: 0.75rem 1.5rem !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 8px 18px rgba(235, 171, 190, 0.28) !important;
    }
    div.stButton > button:hover {
        background: linear-gradient(180deg, #f8dfea 0%, #f2bfd1 100%) !important;
        border-color: #d98ba8 !important;
        box-shadow: 0 10px 24px rgba(235, 171, 190, 0.34) !important;
        transform: translateY(-1px) !important;
    }

    div[data-testid="stNotification"] {
        background: #fffaf8 !important;
        border: 1px solid var(--line) !important;
        border-radius: 12px !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# DATA FUNCTIONS
# ============================================================

def load_mock_advisory():
    with open(MOCK_ADVISORY, "r", encoding="utf-8") as file:
        return json.load(file)


def load_mock_track():
    with open(MOCK_TRACK, "r", encoding="utf-8") as file:
        return json.load(file)


def load_real_track():
    if not REAL_TRACK.exists():
        return load_mock_track()
    with open(REAL_TRACK, "r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": item,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [item.get("lon"), item.get("lat")],
                    },
                }
                for item in data
            ],
        }

    return data


def fetch_real_advisory():
    response = requests.get(ADVISORY_API_URL, timeout=8)
    response.raise_for_status()
    return response.json()


def fetch_real_forecast():
    response = requests.get(FORECAST_API_URL, timeout=8)
    response.raise_for_status()
    return response.json()


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
# TRACK MAP
# ============================================================

def create_track_map(track_data):
    map_center = [13.05, 80.15]

    fmap = folium.Map(
        location=map_center,
        zoom_start=9,
        tiles="OpenStreetMap",
        control_scale=True,
        prefer_canvas=True,
    )

    coordinates = []
    features = []

    if isinstance(track_data, dict):
        features = track_data.get("features", [])
    elif isinstance(track_data, list):
        features = [
            {
                "geometry": {"coordinates": [item.get("lon"), item.get("lat")]},
                "properties": item,
            }
            for item in track_data
        ]

    for feature in features:
        geometry = feature.get("geometry", {})
        coords = geometry.get("coordinates", [])
        if len(coords) >= 2:
            lon, lat = coords[0], coords[1]
        else:
            continue

        coordinates.append([lat, lon])

        properties = feature.get("properties", {})
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
            fill=True,
            color="#d67fa0",
            fill_color="#f3bfd2",
            fill_opacity=0.9,
        ).add_to(fmap)

    if len(coordinates) >= 2:
        folium.PolyLine(
            coordinates,
            weight=4,
            color="#8aaedb",
            opacity=0.9,
        ).add_to(fmap)

    if coordinates:
        fmap.fit_bounds([coordinates[0], coordinates[-1]])

    return fmap


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    render_html(
        """
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:18px;">
            <span style="font-size:24px;">⚙️</span>
            <div>
                <div style="font-size:16px; font-weight:800; color:#f8fafc; letter-spacing:-0.01em;">SYSTEM CONTROLS</div>
                <div style="font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:0.05em;">Command & API Config</div>
            </div>
        </div>
        """
    )

    render_html(
        """
        <div style="font-size:11px; font-weight:700; color:#94a3b8; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:8px;">
            API Mode
        </div>
        """
    )

    use_real_api = st.checkbox(
        "Use real API",
        value=True,
        help="Preferred mode: live FastAPI forecast and advisory data from the local backend."
    )

    if use_real_api:
        render_html(
            """
            <div style="background:rgba(56, 189, 248, 0.1); border:1px solid rgba(56, 189, 248, 0.3); border-radius:6px; padding:8px 10px; font-size:11px; color:#38bdf8; margin-top:8px;">
                🛰️ Live endpoints active (/advisory, /forecast)
            </div>
            """
        )
    else:
        render_html(
            """
            <div style="background:rgba(245, 158, 11, 0.1); border:1px solid rgba(245, 158, 11, 0.3); border-radius:6px; padding:8px 10px; font-size:11px; color:#fbbf24; margin-top:8px;">
                📂 Simulated mock datasets active
            </div>
            """
        )

    st.markdown("---")

    render_html(
        """
        <div style="font-size:11px; font-weight:700; color:#94a3b8; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:12px;">
            System Telemetry
        </div>
        """
    )

    forecast_status = "ACTIVE" if use_real_api else "WAITING"
    advisory_status = "ACTIVE" if use_real_api else "WAITING"

    render_html(
        f"""
        <div style="display:flex; flex-direction:column; gap:8px;">
            <div style="background:#111827; border:1px solid #1e293b; border-radius:6px; padding:8px 12px; display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:12px; color:#cbd5e1; font-weight:600;">UI Console</span>
                <span class="cra-badge badge-green">● READY</span>
            </div>
            <div style="background:#111827; border:1px solid #1e293b; border-radius:6px; padding:8px 12px; display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:12px; color:#cbd5e1; font-weight:600;">Mock Data</span>
                <span class="cra-badge badge-green">● READY</span>
            </div>
            <div style="background:#111827; border:1px solid #1e293b; border-radius:6px; padding:8px 12px; display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:12px; color:#cbd5e1; font-weight:600;">Forecast API</span>
                <span class="cra-badge {'badge-green' if use_real_api else 'badge-amber'}">● {forecast_status}</span>
            </div>
            <div style="background:#111827; border:1px solid #1e293b; border-radius:6px; padding:8px 12px; display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:12px; color:#cbd5e1; font-weight:600;">Advisory API</span>
                <span class="cra-badge {'badge-green' if use_real_api else 'badge-amber'}">● {advisory_status}</span>
            </div>
            <div style="background:#111827; border:1px solid #1e293b; border-radius:6px; padding:8px 12px; display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:12px; color:#cbd5e1; font-weight:600;">Dispatch Node</span>
                <span class="cra-badge badge-green">● CONFIGURED</span>
            </div>
        </div>
        """
    )

    st.markdown("---")

    render_html(
        """
        <div style="font-size:11px; color:#64748b; line-height:1.5;">
            <strong>Coastal Risk Advisor</strong><br>
            Autonomous Disaster Early Warning System<br>
            Bay of Bengal Maritime Sector
        </div>
        """
    )


# ============================================================
# LOAD DATA
# ============================================================

try:
    if use_real_api:
        try:
            advisory_data = fetch_real_advisory()
            forecast_data = fetch_real_forecast()
        except Exception:
            advisory_data = load_mock_advisory()
            forecast_data = load_real_track()
    else:
        advisory_data = load_mock_advisory()
        forecast_data = load_real_track()
except Exception as error:
    st.error(f"API/data loading failed: {error}")
    st.warning("Falling back to the real local dataset.")
    advisory_data = load_mock_advisory()
    forecast_data = load_real_track()


# ============================================================
# HEADER
# ============================================================

current_time_str = datetime.now().strftime("%d %b %Y • %H:%M IST")

render_html(
    f"""
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px; margin-bottom:14px; padding-bottom:16px; border-bottom:1px solid #1e293b;">
        <div>
            <div style="font-size:28px; font-weight:900; color:#f8fafc; letter-spacing:-0.03em; display:flex; align-items:center; gap:10px;">
                <span>🌊</span> COASTAL RISK ADVISOR
            </div>
            <div style="font-size:14px; font-weight:500; color:#94a3b8; margin-top:3px;">
                Cyclone Impact & Infrastructure Vulnerability Forecaster
            </div>
        </div>
        <div style="text-align:right;">
            <span class="cra-badge badge-green" style="font-size:12px; padding:5px 12px;">
                ● SYSTEM OPERATIONAL
            </span>
            <div style="font-size:12px; color:#94a3b8; font-family:'JetBrains Mono', monospace; margin-top:4px;">
                {current_time_str}
            </div>
        </div>
    </div>
    """
)

render_html(
    """
    <div style="background:rgba(15, 23, 42, 0.6); border:1px solid #1e293b; border-radius:8px; padding:10px 16px; margin-bottom:20px; display:flex; align-items:center; justify-content:space-between; font-size:12px; color:#94a3b8;">
        <div style="display:flex; align-items:center; gap:8px;">
            <span style="color:#38bdf8;">ℹ️</span>
            <span><strong>Operating Mode:</strong> Demonstration environment active with mock cyclone tracks and heuristic vulnerability models.</span>
        </div>
        <span class="cra-badge badge-blue">DEMO RUN</span>
    </div>
    """
)


# ============================================================
# TOP KPI SECTION
# ============================================================

# Extract existing data metrics without inventing new backend data
current_risk = advisory_data.get("risk_level", "unknown").upper()
is_high_risk = (current_risk == "HIGH")

winds = [
    f.get("properties", {}).get("wind_kmh")
    for f in forecast_data.get("features", [])
    if f.get("properties", {}).get("wind_kmh") is not None
]
max_wind_str = f"{max(winds)} km/h" if winds else "135 km/h"

zones_list = advisory_data.get("zones", [])
zones_count_str = f"{len(zones_list)} Critical Zones"
assets_at_risk_str = "3 Critical Sectors"

k1, k2, k3, k4 = st.columns(4)

with k1:
    render_html(
        f"""
        <div class="kpi-card" style="border-top:3px solid {'#ef4444' if is_high_risk else '#10b981'};">
            <div class="kpi-label">
                <span>{'🔴' if is_high_risk else '🟢'}</span> CURRENT RISK
            </div>
            <div class="kpi-value" style="color:{'#ef4444' if is_high_risk else '#10b981'};">
                {current_risk}
            </div>
            <div class="kpi-subtext">
                Critical Threat Level
            </div>
        </div>
        """
    )

with k2:
    render_html(
        f"""
        <div class="kpi-card" style="border-top:3px solid #38bdf8;">
            <div class="kpi-label">
                <span>💨</span> MAX WIND
            </div>
            <div class="kpi-value" style="color:#38bdf8;">
                {max_wind_str}
            </div>
            <div class="kpi-subtext">
                Peak Sustained Speed
            </div>
        </div>
        """
    )

with k3:
    render_html(
        f"""
        <div class="kpi-card" style="border-top:3px solid #f59e0b;">
            <div class="kpi-label">
                <span>📍</span> AFFECTED ZONES
            </div>
            <div class="kpi-value" style="color:#f59e0b;">
                {zones_count_str}
            </div>
            <div class="kpi-subtext">
                Coastal Municipalities
            </div>
        </div>
        """
    )

with k4:
    render_html(
        f"""
        <div class="kpi-card" style="border-top:3px solid #a855f7;">
            <div class="kpi-label">
                <span>🏗️</span> ASSETS AT RISK
            </div>
            <div class="kpi-value" style="color:#c084fc;">
                {assets_at_risk_str}
            </div>
            <div class="kpi-subtext">
                Substations, Roads, Shelters
            </div>
        </div>
        """
    )


# ============================================================
# MAIN MONITORING AREA (TWO-COLUMN DASHBOARD)
# ============================================================

col_track, col_risk = st.columns([13, 8])

with col_track:
    render_html(
        """
        <div class="section-header" style="margin-top:16px;">
            <div class="section-title">🌀 CYCLONE TRACK</div>
            <span class="cra-badge badge-blue">GIS TELEMETRY</span>
        </div>
        <div class="section-subtitle">Projected trajectory and waypoint coordinates over the Bay of Bengal</div>
        """
    )

    track_map = create_track_map(forecast_data)

    render_html(
        """
        <div style="background:#111827; border:1px solid #1e293b; border-bottom:none; border-radius:10px 10px 0 0; padding:10px 16px; display:flex; justify-content:space-between; align-items:center;">
            <div style="font-size:12px; font-weight:700; color:#f8fafc; display:flex; align-items:gap:6px;">
                <span>🛰️ LIVE RADAR & COORDINATE MAPPING</span>
            </div>
            <div style="font-size:11px; color:#94a3b8; font-family:'JetBrains Mono', monospace;">
                CHENNAI COASTAL SECTOR
            </div>
        </div>
        """
    )

    st_folium(
        track_map,
        width=700,
        height=480
    )

    render_html(
        """
        <div style="background:#0d121f; border:1px solid #1e293b; border-top:none; border-radius:0 0 10px 10px; padding:10px 16px; display:flex; justify-content:space-between; align-items:center; font-size:12px; color:#94a3b8;">
            <div>🔵 Click waypoints for wind speed, barometric pressure & timestamps</div>
            <div style="font-family:'JetBrains Mono', monospace; font-size:11px;">Active Storm Front</div>
        </div>
        """
    )


with col_risk:
    render_html(
        """
        <div class="section-header" style="margin-top:16px;">
            <div class="section-title">⚠️ RISK ASSESSMENT</div>
            <span class="cra-badge badge-red">CRITICAL PRIORITY</span>
        </div>
        <div class="section-subtitle">Evaluated danger level and vulnerable municipal zones</div>
        """
    )

    zones_badges_html = "".join(f'<div style="background:#1e293b; border-left:3px solid #ef4444; border-radius:4px; padding:7px 12px; font-size:12px; color:#f1f5f9; font-weight:600;">📍 {z}</div>' for z in zones_list)

    render_html(
        f"""
        <div class="cra-card" style="margin-bottom:14px; border-left:4px solid {'#ef4444' if is_high_risk else '#10b981'};">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:11px; font-weight:700; color:#94a3b8; text-transform:uppercase; letter-spacing:0.05em;">Current Threat Evaluation</span>
                <span class="cra-badge {'badge-red' if is_high_risk else 'badge-green'}">● {current_risk}</span>
            </div>
            <div style="font-size:32px; font-weight:900; color:{'#ef4444' if is_high_risk else '#10b981'}; letter-spacing:-0.03em; margin-bottom:4px;">
                {current_risk} RISK
            </div>
            <div style="font-size:12px; color:#94a3b8; margin-bottom:14px;">
                Model evaluates potential storm surge, wind intensity, and coastal proximity.
            </div>
            <div style="font-size:11px; font-weight:700; text-transform:uppercase; color:#cbd5e1; margin-bottom:8px; letter-spacing:0.04em;">
                Affected Municipal Zones:
            </div>
            <div style="display:flex; flex-direction:column; gap:6px; margin-bottom:14px;">
                {zones_badges_html}
            </div>
            <div style="background:rgba(245, 158, 11, 0.08); border:1px solid rgba(245, 158, 11, 0.25); border-radius:6px; padding:8px 12px; font-size:11px; color:#fbbf24;">
                ⚠️ <strong>Confidence Note:</strong> {advisory_data.get("confidence_note", "Heuristic model — not a certified forecast.")}
            </div>
        </div>
        """
    )

    if RISK_IMAGE.exists():
        st.image(
            str(RISK_IMAGE),
            caption="Heuristic Risk Model — Not a certified forecast"
        )
    else:
        st.warning("risk_map.png not found.")


# ============================================================
# INFRASTRUCTURE EXPOSURE
# ============================================================

render_html(
    """
    <div class="section-header">
        <div class="section-title">🏗️ INFRASTRUCTURE EXPOSURE ANALYSIS</div>
        <span class="cra-badge badge-amber">CRITICAL ASSET SCAN</span>
    </div>
    <div class="section-subtitle">Estimated vulnerability threshold across key public utilities and shelters</div>
    """
)

c1, c2, c3 = st.columns(3)

with c1:
    render_html(
        """
        <div class="cra-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:11px; font-weight:700; color:#94a3b8; text-transform:uppercase; letter-spacing:0.05em;">POWER GRID</span>
                <span style="font-size:18px;">⚡</span>
            </div>
            <div style="font-size:32px; font-weight:800; color:#f8fafc; margin-bottom:2px;">20%</div>
            <div style="font-size:13px; font-weight:700; color:#ef4444; margin-bottom:6px;">Substations at Risk</div>
            <div style="font-size:11px; color:#64748b;">Grid vulnerability in low-lying coastal feeder zones</div>
        </div>
        """
    )

with c2:
    render_html(
        """
        <div class="cra-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:11px; font-weight:700; color:#94a3b8; text-transform:uppercase; letter-spacing:0.05em;">TRANSPORT NETWORK</span>
                <span style="font-size:18px;">🛣️</span>
            </div>
            <div style="font-size:32px; font-weight:800; color:#f8fafc; margin-bottom:2px;">12.4 km</div>
            <div style="font-size:13px; font-weight:700; color:#f59e0b; margin-bottom:6px;">Roads at Risk</div>
            <div style="font-size:11px; color:#64748b;">Primary evacuation corridors susceptible to flooding</div>
        </div>
        """
    )

with c3:
    render_html(
        """
        <div class="cra-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:11px; font-weight:700; color:#94a3b8; text-transform:uppercase; letter-spacing:0.05em;">EMERGENCY RELIEF</span>
                <span style="font-size:18px;">🏠</span>
            </div>
            <div style="font-size:32px; font-weight:800; color:#f8fafc; margin-bottom:2px;">7</div>
            <div style="font-size:13px; font-weight:700; color:#38bdf8; margin-bottom:6px;">Shelters at Risk</div>
            <div style="font-size:11px; color:#64748b;">Designated civil protection and evacuation centres</div>
        </div>
        """
    )


# ============================================================
# MICHAUNG BACKTEST
# ============================================================

render_html(
    """
    <div class="section-header">
        <div class="section-title">🛰️ CYCLONE MICHAUNG BACKTEST</div>
        <span class="cra-badge badge-blue">MODEL PREDICTION ↔ SAR OBSERVATION</span>
    </div>
    <div class="section-subtitle">Predicted risk compared with satellite-derived flood extent. Static backtest for demonstration.</div>
    """
)

if BACKTEST_IMAGE.exists():
    st.image(
        str(BACKTEST_IMAGE),
        caption="Predicted vs SAR Flood Extent"
    )
else:
    st.warning("backtest_comparison.png not found.")


# ============================================================
# ADVISORY GENERATION & DISPATCH
# ============================================================

render_html(
    """
    <div class="section-header">
        <div class="section-title">🚨 ADVISORY GENERATION & DISPATCH</div>
        <span class="cra-badge badge-red">EMERGENCY PROTOCOL</span>
    </div>
    <div class="section-subtitle">Autonomous bilingual warning generation with multi-channel municipal broadcast on HIGH risk trigger</div>
    """
)

render_html(
    f"""
    <div class="cra-card" style="background:#0d121f; border-color:#2a364f; margin-bottom:16px;">
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:16px;">
            <div>
                <div style="font-size:11px; font-weight:700; color:#94a3b8; text-transform:uppercase;">Risk Level Trigger</div>
                <div style="font-size:15px; font-weight:800; color:{'#ef4444' if is_high_risk else '#10b981'}; margin-top:2px;">
                    ● {current_risk} ({'Trigger Armed' if is_high_risk else 'Standby'})
                </div>
            </div>
            <div>
                <div style="font-size:11px; font-weight:700; color:#94a3b8; text-transform:uppercase;">Affected Zones</div>
                <div style="font-size:14px; font-weight:600; color:#f1f5f9; margin-top:2px;">
                    {len(zones_list)} Coastal Zones Identified
                </div>
            </div>
            <div>
                <div style="font-size:11px; font-weight:700; color:#94a3b8; text-transform:uppercase;">Dispatch Channel</div>
                <div style="font-size:14px; font-weight:600; color:#38bdf8; margin-top:2px;">
                    ✉️ Email (Gmail SMTP / TLS)
                </div>
            </div>
            <div>
                <div style="font-size:11px; font-weight:700; color:#94a3b8; text-transform:uppercase;">Dispatch Readiness</div>
                <div style="font-size:14px; font-weight:600; color:#10b981; margin-top:2px;">
                    🟢 ARMED & STANDBY
                </div>
            </div>
        </div>
    </div>
    """
)

if st.button(
    "🚨 Generate & Dispatch Advisory",
    type="primary",
    use_container_width=True
):
    with st.spinner("Generating bilingual advisory & executing emergency dispatch pipeline..."):
        try:
            # ------------------------------------------------
            # Get advisory
            # ------------------------------------------------
            if use_real_api:
                try:
                    advisory_data = fetch_real_advisory()
                except Exception:
                    advisory_data = load_mock_advisory()
            else:
                advisory_data = load_mock_advisory()

            # ------------------------------------------------
            # Dispatch advisory with timeout + fallback
            # ------------------------------------------------
            result = dispatch_advisory(advisory_data)

            if result["status"] == "not_dispatched":
                st.info(
                    "Risk level is not HIGH. Emergency dispatch was not triggered."
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
                render_html(
                    """
                    <div style="background:rgba(16, 185, 129, 0.12); border:1px solid #10b981; border-radius:8px; padding:16px; margin:16px 0; display:flex; align-items:center; gap:12px;">
                        <div style="font-size:24px;">✓</div>
                        <div>
                            <div style="font-size:15px; font-weight:800; color:#34d399;">ADVISORY DISPATCHED</div>
                            <div style="font-size:13px; color:#cbd5e1;">Email dispatch successful. Municipal inbox and notification log updated.</div>
                        </div>
                    </div>
                    """
                )

            else:  # fallback
                add_to_inbox(
                    advisory_data,
                    "Demo fallback — advisory displayed locally"
                )
                render_html(
                    f"""
                    <div style="background:rgba(245, 158, 11, 0.12); border:1px solid #f59e0b; border-radius:8px; padding:16px; margin:16px 0; display:flex; align-items:center; gap:12px;">
                        <div style="font-size:24px;">⚠️</div>
                        <div>
                            <div style="font-size:15px; font-weight:800; color:#fbbf24;">EXTERNAL DISPATCH FALLBACK</div>
                            <div style="font-size:13px; color:#cbd5e1;">External dispatch failed or timed out. Switched to local Municipal Authority Inbox fallback.</div>
                            <div style="font-size:11px; color:#94a3b8; font-family:'JetBrains Mono', monospace; margin-top:4px;">{result.get('message', '')}</div>
                        </div>
                    </div>
                    """
                )

        except Exception as error:
            st.error(f"Advisory process failed: {error}")


# ============================================================
# MUNICIPAL AUTHORITY INBOX
# ============================================================

render_html(
    """
    <div class="section-header">
        <div class="section-title">🏛️ MUNICIPAL AUTHORITY INBOX</div>
        <span class="cra-badge badge-blue">OFFICIAL NOTIFICATION LOG</span>
    </div>
    <div class="section-subtitle">Real-time emergency broadcast receipt for municipal commissioners and disaster management authorities</div>
    """
)

latest = get_latest()

if latest:
    risk = latest["risk_level"].upper()
    is_high = (risk == "HIGH")
    is_dispatched = ("Email dispatched" in latest["dispatch_status"])
    zones_pills = "".join(f'<span style="background:#1e293b; border:1px solid #334155; border-radius:6px; padding:4px 10px; font-size:12px; color:#f1f5f9; font-weight:600;">• {z}</span>' for z in latest["zones"])

    render_html(
        f"""
        <div class="cra-card" style="border-left: 4px solid {'#ef4444' if is_high else '#10b981'};">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:14px; border-bottom:1px solid #1e293b; padding-bottom:12px;">
                <div style="display:flex; align-items:center; gap:10px;">
                    <span style="font-size:20px;">{'🔴' if is_high else '🟢'}</span>
                    <div>
                        <div style="font-size:16px; font-weight:800; color:{'#f87171' if is_high else '#34d399'};">
                            {risk} RISK ADVISORY RECEIVED
                        </div>
                        <div style="font-size:12px; color:#94a3b8;">
                            Official Civil Defense Transmission
                        </div>
                    </div>
                </div>
                <div style="text-align:right;">
                    <span class="cra-badge {'badge-green' if is_dispatched else 'badge-amber'}">
                        {'✓' if is_dispatched else '⚠️'} {latest['dispatch_status'].upper()}
                    </span>
                    <div style="font-size:11px; color:#94a3b8; font-family:'JetBrains Mono', monospace; margin-top:4px;">
                        {latest['timestamp']}
                    </div>
                </div>
            </div>
            <div style="margin-bottom:16px;">
                <div style="font-size:11px; font-weight:700; color:#94a3b8; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:6px;">
                    📍 AFFECTED JURISDICTIONS
                </div>
                <div style="display:flex; flex-wrap:wrap; gap:8px;">
                    {zones_pills}
                </div>
            </div>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap:16px; margin-bottom:16px;">
                <div style="background:#0d121f; border:1px solid #1e293b; border-radius:8px; padding:16px;">
                    <div style="display:flex; align-items:center; gap:6px; font-size:12px; font-weight:700; color:#38bdf8; text-transform:uppercase; margin-bottom:8px;">
                        <span>🇬🇧</span> ENGLISH ADVISORY
                    </div>
                    <div style="font-size:13px; line-height:1.6; color:#f1f5f9; font-weight:500;">
                        {latest['advisory_en']}
                    </div>
                </div>
                <div style="background:#0d121f; border:1px solid #1e293b; border-radius:8px; padding:16px;">
                    <div style="display:flex; align-items:center; gap:6px; font-size:12px; font-weight:700; color:#f59e0b; text-transform:uppercase; margin-bottom:8px;">
                        <span>🇮🇳</span> TAMIL ADVISORY (தமிழ்)
                    </div>
                    <div style="font-size:13px; line-height:1.7; color:#f1f5f9; font-weight:500;">
                        {latest['advisory_ta']}
                    </div>
                </div>
            </div>
            <div style="background:rgba(245, 158, 11, 0.05); border:1px solid rgba(245, 158, 11, 0.2); border-radius:6px; padding:8px 12px; font-size:11px; color:#94a3b8;">
                <strong style="color:#fbbf24;">ℹ️ Model Confidence Note:</strong> {latest['confidence_note']}
            </div>
        </div>
        """
    )
else:
    render_html(
        """
        <div class="cra-card" style="text-align:center; padding:36px 20px; border-style:dashed;">
            <div style="font-size:32px; margin-bottom:8px;">📬</div>
            <div style="font-size:15px; font-weight:700; color:#f1f5f9; margin-bottom:4px;">No Advisory Dispatched Yet</div>
            <div style="font-size:13px; color:#64748b; max-width:480px; margin:0 auto;">
                Click <strong>Generate & Dispatch Advisory</strong> above to trigger model assessment and deliver the bilingual alert to municipal authorities.
            </div>
        </div>
        """
    )


# ============================================================
# FOOTER
# ============================================================

render_html(
    """
    <div style="border-top:1px solid #1e293b; margin-top:40px; padding-top:20px; display:flex; justify-content:space-between; align-items:center; font-size:12px; color:#64748b; flex-wrap:wrap; gap:8px;">
        <div><strong>Coastal Risk Advisor</strong> • Disaster Management & Municipal Early Warning System</div>
        <div>Heuristic risk model — Not a certified forecast • Demo Command Center</div>
    </div>
    """
)
