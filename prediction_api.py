from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel

MODEL_PATH = Path(__file__).resolve().parent / "artifacts" / "randomforest_hazard_model.pkl"
FEATURE_COLUMNS = [
    "elevation_m",
    "rainfall_mm",
    "slope_deg",
    "surge_risk",
    "coastal_flag",
]

app = FastAPI(title="Disaster Risk Prediction API", version="1.1.0")


class PredictionRequest(BaseModel):
    elevation_m: float
    rainfall_mm: float
    slope_deg: float
    surge_risk: float
    coastal_flag: int = 0


class PredictionResponse(BaseModel):
    hazard_label: int
    probability_high_risk: float
    model_path: str
    feature_columns: list[str]


def _load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model artifact not found at {MODEL_PATH}. Train the model first.")
    return joblib.load(MODEL_PATH)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest) -> PredictionResponse:
    model = _load_model()
    features = np.array(
        [[
            float(request.elevation_m),
            float(request.rainfall_mm),
            float(request.slope_deg),
            float(request.surge_risk),
            int(request.coastal_flag),
        ]],
        dtype=float,
    )
    probability = float(model.predict_proba(features)[0, 1])
    label = int(probability >= 0.5)
    return PredictionResponse(
        hazard_label=label,
        probability_high_risk=probability,
        model_path=str(MODEL_PATH),
        feature_columns=FEATURE_COLUMNS,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("prediction_api:app", host="0.0.0.0", port=8001, reload=False)
