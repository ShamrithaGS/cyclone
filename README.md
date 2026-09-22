You can replace your README with this:

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
Core Workflow
Input Data
   |
   +-- Cyclone Track
   +-- DEM / Elevation
   +-- Rainfall
   +-- Infrastructure
   +-- Sentinel-1 SAR
          |
          v
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
Key Features
Cyclone track visualization
Coastal risk assessment
Infrastructure exposure analysis
Cyclone Michaung backtesting
Sentinel-1 SAR flood comparison
AI-assisted advisory generation
English and Tamil emergency advisories
Risk-based email dispatch
Municipal authority inbox
Mock data and real API modes
Streamlit-based monitoring dashboard
Risk Assessment Pipeline
Cyclone Track
      |
      v
Holland Wind Model
      |
      +------> Wind Risk
      |
DEM / Elevation
      |
      +------> Elevation Risk
      |
Rainfall + Slope
      |
      +------> Flood / Landslide Risk
      |
      v
Risk Raster
      |
      v
Infrastructure Overlay
      |
      +----> Substations
      +----> Roads
      +----> Shelters
      |
      v
Exposure Analysis
Michaung Backtesting
Before SAR Image
        |
        v
Change Detection
        |
        v
Observed Flood Extent
        ^
        |
        | Comparison
        |
Predicted Risk Raster
        ^
        |
Risk Model

The backtesting module compares the predicted risk pattern with satellite-derived flood extent from Cyclone Michaung.

Advisory and Dispatch Flow
Risk Assessment
      |
      v
Advisory Generation
      |
      v
Risk Level
      |
      +----------------+
      |                |
     HIGH          NOT HIGH
      |                |
      v                v
Email Dispatch     No Dispatch
      |
      v
Municipal Inbox

External dispatch failures are handled using a local demonstration fallback.

Technology Stack
Component	Technology
Frontend	Streamlit
Interactive Map	Folium
Backend APIs	FastAPI
Machine Learning	Python
AI Advisory	Gemini
Satellite Validation	Sentinel-1 SAR
Data Processing	NumPy, Pandas, Raster Processing
Communication	SMTP Email
Version Control	Git / GitHub
Project Structure
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
Running the Application

Install dependencies:

pip install -r requirements.txt

Configure the required environment variables in .env.

Run the Streamlit application:

streamlit run app.py
Demo Flow
Launch Dashboard
       |
       v
View Cyclone Track
       |
       v
Review Risk Assessment
       |
       v
Review Infrastructure Exposure
       |
       v
View Michaung Backtest
       |
       v
Generate Advisory
       |
       v
If Risk = HIGH
       |
       v
Dispatch Email
       |
       v
Municipal Authority Inbox
Disclaimer

The current risk assessment uses a heuristic demonstration model and is not a certified cyclone, storm-surge, flood, or evacuation forecast.
