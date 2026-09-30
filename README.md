# Coastal Risk Advisor

## Cyclone Impact & Infrastructure Vulnerability Forecaster

A decision-support system for estimating cyclone-related coastal risk, infrastructure vulnerability, and generating emergency advisories for affected zones.

---

## System Overview

```text
Cyclone Track
     |
     v
+-----------------------+
| Risk & Vulnerability  |
| Engine                |
|                       |
| Wind + DEM + Rainfall |
+-----------+-----------+
            |
            v
+-----------------------+
| Risk Assessment       |
| & Infrastructure      |
| Exposure              |
+-----------+-----------+
            |
            v
+-----------------------+
| Gemini Advisory       |
| Generation            |
+-----------+-----------+
            |
            v
+-----------------------+
| Bilingual Advisory    |
| English + Tamil       |
+-----------+-----------+
            |
            v
+-----------------------+
| Dispatch Layer        |
| Email / Mock Inbox    |
+-----------+-----------+
            |
            v
   Municipal Authority
```

## Core Workflow

**Input Data:**
- Cyclone Track
- DEM / Elevation
- Rainfall
- Infrastructure
- Sentinel-1 SAR

**Processing Pipeline:**
```
Risk Prediction
       |
       v
Infrastructure Exposure
       |
       v
AI Advisory Generation
       |
       v
Risk-Level Decision
       |
    HIGH?
    /   \
  YES    NO
   |      |
   v      v
Dispatch  No Dispatch
   |
   v
Municipal Inbox
```

## Key Features

- Cyclone track visualization
- Coastal risk assessment
- Infrastructure exposure analysis
- Cyclone Michaung backtesting
- Sentinel-1 SAR flood comparison
- AI-assisted advisory generation
- English and Tamil emergency advisories
- Risk-based email dispatch
- Municipal authority inbox
- Mock data and real API modes
- Streamlit-based monitoring dashboard

## Risk Assessment Pipeline

```
Cyclone Track → Holland Wind Model → Wind Risk
                                   ↓
DEM / Elevation → Elevation Risk ──┤
                                   ↓
Rainfall + Slope → Flood/Landslide Risk
                                   ↓
              Risk Raster
                  |
                  v
         Infrastructure Overlay
         (Substations, Roads, Shelters)
                  |
                  v
         Exposure Analysis
```

## Michaung Backtesting

Compares the predicted risk pattern with satellite-derived flood extent from Cyclone Michaung:

```
Before SAR Image → Change Detection → Observed Flood Extent
                                              ↑
                                         Comparison
                                              ↑
                               Predicted Risk Raster
                                    (from Risk Model)
```

## Advisory and Dispatch Flow

```
Risk Assessment
       |
       v
Advisory Generation
       |
       v
Risk Level
       |
    +---------+
    |         |
  HIGH    NOT HIGH
    |         |
    v         v
Email     No Dispatch
Dispatch
    |
    v
Municipal Inbox
```

**Note:** External dispatch failures are handled using a local demonstration fallback.

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Frontend | Streamlit |
| Interactive Map | Folium |
| Backend APIs | FastAPI |
| Machine Learning | Python |
| AI Advisory | Gemini |
| Satellite Validation | Sentinel-1 SAR |
| Data Processing | NumPy, Pandas, Raster Processing |
| Communication | SMTP Email |
| Version Control | Git / GitHub |

## Project Structure

```
coastal-risk-advisor/
|
├── app.py
|
├── dispatch/
│   ├── __init__.py
│   ├── email_dispatch.py
│   └── mock_inbox.py
|
├── mock/
│   ├── advisory.json
│   └── track.geojson
|
├── assets/
│   ├── risk_map.png
│   └── backtest_comparison.png
|
├── requirements.txt
├── test_email.py
└── .gitignore
```

## Running the Application

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables** in `.env`

3. **Run the Streamlit application:**
   ```bash
   streamlit run app.py
   ```

## Deployment on Render

The `render.yaml` Blueprint defines separate FastAPI and Streamlit web services.

1. Push this repository to GitHub
2. In Render, choose **New + → Blueprint**
3. Select this repository and apply

**Environment Variables:**
- Set `GEMINI_API_KEY` on the API service if live Gemini advisory generation is enabled
- Set `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD`, and `TEST_EMAIL` on the dashboard service if email dispatch is enabled

## Demo Flow

```
1. Launch Dashboard
       ↓
2. View Cyclone Track
       ↓
3. Review Risk Assessment
       ↓
4. Review Infrastructure Exposure
       ↓
5. View Michaung Backtest
       ↓
6. Generate Advisory
       ↓
7. Check Risk Level (HIGH?)
       ↓
8. If HIGH → Dispatch Email → Municipal Authority Inbox
```

## Disclaimer

The current risk assessment uses a heuristic demonstration model and is **not a certified cyclone, storm-surge, flood, or evacuation forecast**.
