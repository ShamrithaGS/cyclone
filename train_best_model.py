from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from feature_engineering import FEATURE_COLUMNS, load_labeled_dataset

ROOT = Path(__file__).resolve().parent
ARTIFACT_DIR = ROOT / "artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True)


def train_model(dataset_path: str | Path | None = None) -> tuple[dict[str, float], Pipeline, dict[str, object]]:
    df = load_labeled_dataset(dataset_path)
    X = df[FEATURE_COLUMNS].copy()
    y = df["label"].copy()

    X_train, X_temp, y_train, y_temp = train_test_split(
        X,
        y,
        test_size=0.4,
        random_state=42,
        stratify=y,
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp,
        y_temp,
        test_size=0.5,
        random_state=42,
        stratify=y_temp,
    )

    models: dict[str, Pipeline] = {
        "RandomForest": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=250,
                        max_depth=None,
                        min_samples_leaf=5,
                        class_weight="balanced_subsample",
                        random_state=42,
                    ),
                ),
            ]
        ),
        "HistGradientBoosting": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                (
                    "model",
                    HistGradientBoostingClassifier(
                        learning_rate=0.08,
                        max_depth=8,
                        max_iter=250,
                        random_state=42,
                    ),
                ),
            ]
        ),
    }

    best_name = ""
    best_model = None
    best_metrics: dict[str, float] = {}
    best_score = -1.0

    for name, model in models.items():
        model.fit(X_train, y_train)
        y_pred = model.predict(X_val)
        metrics = {
            "accuracy": float(accuracy_score(y_val, y_pred)),
            "precision": float(precision_score(y_val, y_pred, zero_division=0)),
            "recall": float(recall_score(y_val, y_pred, zero_division=0)),
            "f1": float(f1_score(y_val, y_pred, zero_division=0)),
        }
        try:
            metrics["roc_auc"] = float(roc_auc_score(y_val, model.predict_proba(X_val)[:, 1]))
        except Exception:
            metrics["roc_auc"] = float("nan")

        if metrics["f1"] > best_score:
            best_score = metrics["f1"]
            best_name = name
            best_model = model
            best_metrics = metrics

    if best_model is None:
        raise RuntimeError("No model could be trained")

    y_pred_test = best_model.predict(X_test)
    report = classification_report(y_test, y_pred_test, zero_division=0)
    summary = {
        "best_model": best_name,
        "feature_columns": FEATURE_COLUMNS,
        "train_rows": int(len(X_train)),
        "val_rows": int(len(X_val)),
        "test_rows": int(len(X_test)),
        "positive_label_rate": float(y.mean()),
        "validation_metrics": best_metrics,
        "test_classification_report": report,
    }
    return best_metrics, best_model, summary


def main() -> None:
    metrics, model, summary = train_model()
    model_path = ARTIFACT_DIR / "randomforest_hazard_model.pkl"
    joblib.dump(model, model_path)

    summary["artifact_path"] = str(model_path)
    summary["metrics"] = metrics

    with open(ARTIFACT_DIR / "best_model_summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    print(json.dumps(metrics, indent=2))
    print("\nTest classification report:\n" + summary["test_classification_report"])
    print(f"Saved model: {model_path}")


if __name__ == "__main__":
    main()
