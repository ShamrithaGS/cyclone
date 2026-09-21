from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

load_dotenv()

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


MOCK_FORECAST = {
    "region": "Chennai-Cuddalore coastal stretch",
    "cyclone_name": "Test-2026",
    "exposure": {
        "substations_at_risk": 3,
        "roads_flooded_km": 12,
        "shelters_at_risk": 5,
        "max_surge_m": 1.8,
        "max_wind_kmh": 125,
    },
}

CACHED_ZONE_FALLBACK = [
    {
        "name": "North of Chennai port",
        "evidence": "High-intensity cluster sits in the upper-left section of the map, consistent with a coastal hotspot north of Chennai port.",
    },
    {
        "name": "Along NH-45 near Cuddalore",
        "evidence": "A second red-hot region appears along the eastern corridor, matching a transport-linked risk zone near NH-45 and Cuddalore.",
    },
    {
        "name": "South of the industrial belt",
        "evidence": "A smaller but intense cluster appears in the lower-central section, suggesting concentrated flooding and wind exposure near the southern urban edge.",
    },
]

CACHED_ADVISORY_EN = (
    "1) Evacuate zones north of Chennai port and along NH-45 near Cuddalore within 3 hours. "
    "Keep a 2 km buffer around shelters at risk.\n"
    "2) De-energize substations S-12, S-19, and S-27; close the NH-45 coastal segment and feeder roads near the flood pockets.\n"
    "3) Confidence note: this is a heuristic decision-support model, not a certified forecast; verify with local field teams before full mobilization."
)

CACHED_ADVISORY_TA = (
    "1) சென்னை துறைமுகம் வடபுறம் மற்றும் கuddalore அருகே NH-45 பகுதிகளில் உள்ள மண்டலங்கள் 3 மணிநேரத்திற்குள் வெளியேறுங்கள். "
    "தீங்கு உள்ள பாதுகாப்பு மையங்களின் 2 கி.மீ. சுற்றளவை பராமரிக்கவும்.\n"
    "2) S-12, S-19, S-27 துணை மின் நிலையங்களை அணைக்கவும்; வெள்ளம் பாதித்த NH-45 கடலோரப் பகுதியும் அருகிலுள்ள சாலைகளும் மூடப்பட வேண்டும்.\n"
    "3) நம்பிக்கை குறிப்பு: இது ஒரு அனுமானக் கட்டமைப்பு கருவி, சான்றிதழ் பெற்ற முன்னறிவிப்பு அல்ல; முழுப் பணிகளுக்கு முன் உள்ளூர் தள பணியாளர்களால் உறுதிப்படுத்தவும்."
)

CACHED_CONFIDENCE_NOTE = "Heuristic model alert: risk levels here are derived from estimate-based exposure inputs, not a certified meteorological forecast."


def compute_risk_level(exposure: dict[str, Any]) -> str:
    max_surge = float(exposure.get("max_surge_m", 0.0))
    max_wind = float(exposure.get("max_wind_kmh", 0.0))
    if max_surge >= 1.5 or max_wind >= 120:
        return "high"
    if max_surge >= 0.8:
        return "medium"
    return "low"


def run_with_timeout(fn: Callable[..., Any], args: tuple[Any, ...], timeout: float = 8) -> Any:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn, *args)
        return future.result(timeout=timeout)


def call_with_timeout(fn: Callable[..., Any], *args: Any, timeout: float = 8, cached_fallback: Any = None) -> Any:
    try:
        result = run_with_timeout(fn, args, timeout=timeout)
        if result is None:
            return cached_fallback
        if isinstance(result, str) and result.strip() == "":
            return cached_fallback
        return result
    except FutureTimeoutError:
        return cached_fallback
    except Exception:
        return cached_fallback


def verify_gemini_auth(api_key: str | None = None) -> str:
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY is missing")
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content("Respond with 'ok' only.")
        return _extract_text_from_response(response).strip() or "ok"
    except Exception:
        try:
            from google import genai
            client = genai.Client(api_key=key)
            response = client.models.generate_content(model="gemini-2.0-flash", contents=[{"text": "Respond with 'ok' only."}])
            return _extract_text_from_response(response).strip() or "ok"
        except Exception as exc:
            raise RuntimeError(f"Gemini authentication or SDK setup failed: {exc}")


def generate_risk_map(seed: int | None = None, shape: tuple[int, int] = (32, 32)) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.random(shape) * 0.35
    y, x = np.indices(shape)
    centers = [
        (
            int(rng.integers(4, shape[0] // 3)),
            int(rng.integers(3, shape[1] // 2)),
            0.9,
            4.5,
        ),
        (
            int(rng.integers(shape[0] // 2, shape[0] - 3)),
            int(rng.integers(shape[1] // 3, shape[1] - 3)),
            0.95,
            5.0,
        ),
        (
            int(rng.integers(shape[0] // 3, shape[0] - 3)),
            int(rng.integers(2, shape[1] // 3)),
            0.85,
            4.2,
        ),
    ]
    for cy, cx, amp, radius in centers:
        yy = (y - cy) ** 2
        xx = (x - cx) ** 2
        gaussian = amp * np.exp(-((yy + xx) / (2 * radius**2)))
        base += gaussian
    base = np.clip(base, 0, 1)
    return base


def render_risk_map_image(array: np.ndarray, output_path: str | os.PathLike[str]) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 5))
    img = ax.imshow(array, cmap="YlOrRd", interpolation="nearest")
    ax.set_title("Cyclone risk intensity")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    fig.colorbar(img, ax=ax, label="Risk index")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)


def infer_hotspots_from_map(array: np.ndarray) -> list[dict[str, str]]:
    flat = array.ravel()
    threshold = np.quantile(flat, 0.88)
    coords = np.argwhere(array >= threshold)
    if coords.size == 0:
        coords = np.argwhere(array >= np.max(array) * 0.75)
    top_coords = coords[np.argsort(array[tuple(coords.T)])[::-1][:3]]
    zone_names = []
    height, width = array.shape
    for index, (row, col) in enumerate(top_coords):
        hotspot_value = float(array[row, col])
        if row < height * 0.33:
            north_south = "north"
        elif row < height * 0.66:
            north_south = "central"
        else:
            north_south = "south"
        if col < width * 0.33:
            east_west = "west"
        elif col < width * 0.66:
            east_west = "central"
        else:
            east_west = "east"

        if north_south == "north" and east_west == "west":
            name = "North-west coastal belt near Chennai port"
        elif north_south == "north" and east_west == "east":
            name = "North-east corridor along NH-45 near Cuddalore"
        elif north_south == "central" and east_west == "central":
            name = "Central industrial belt"
        elif north_south == "south" and east_west == "east":
            name = "South-east evacuation pocket"
        else:
            name = f"{north_south.title()}-{east_west} risk patch"

        zone_names.append(
            {
                "name": name,
                "evidence": (
                    f"Peak risk value {hotspot_value:.2f} appears in the {north_south} {east_west} sector of the map, creating a distinct hotspot tied to the coast and transport corridor."
                ),
            }
        )
    return zone_names


def _extract_text_from_response(response: Any) -> str:
    if hasattr(response, "text") and response.text:
        return str(response.text)
    if isinstance(response, dict):
        return str(response.get("text") or response.get("content") or "")
    if isinstance(response, list):
        return "\n".join(str(item) for item in response)
    return str(response or "")


def _call_live_gemini_image_reasoning(image_path: str, payload: dict[str, Any]) -> str | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    prompt = (
        "Identify the 3 highest-risk zones visible in this map. Describe their location relative to landmarks "
        "(e.g., 'north of Chennai port', 'along NH-45 near Cuddalore'). Output: a list of zone names, each with what visual evidence in the image supports it."
    )
    try:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            image = plt.imread(image_path)
            response = model.generate_content([prompt, image])
            return _extract_text_from_response(response)
        except Exception:
            from google import genai
            client = genai.Client(api_key=api_key)
            image_bytes = Path(image_path).read_bytes()
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/png", "data": image_bytes}},
                ],
            )
            return _extract_text_from_response(response)
    except Exception:
        return None


def _parse_zone_output(raw_text: str | None, fallback_array: np.ndarray | None = None) -> list[dict[str, str]]:
    if raw_text and raw_text.strip():
        fragments = []
        for line in raw_text.splitlines():
            if line.strip():
                fragments.append(line.strip())
        if fragments:
            parsed = []
            for idx, fragment in enumerate(fragments[:3], start=1):
                label = fragment.split(":", 1)[0].strip() if ":" in fragment else f"Zone {idx}"
                parsed.append({"name": label, "evidence": fragment})
            if parsed:
                return parsed
    if fallback_array is not None:
        return infer_hotspots_from_map(fallback_array)
    return CACHED_ZONE_FALLBACK


def call_risk_zones(image_path: str, payload: dict[str, Any], risk_map: np.ndarray | None = None) -> list[dict[str, str]]:
    def task():
        live_output = _call_live_gemini_image_reasoning(image_path, payload)
        if live_output:
            return _parse_zone_output(live_output, risk_map)
        return _parse_zone_output(None, risk_map)

    return call_with_timeout(task, timeout=8, cached_fallback=_parse_zone_output(None, risk_map))


def _call_live_gemini_advisory(zones: list[dict[str, str]], exposure: dict[str, Any]) -> str | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    prompt = (
        "Generate a 3-part evacuation advisory: (1) evacuation zones and deadlines, (2) infrastructure actions — which substations to de-energize, which roads to close, (3) a confidence note flagging this as a heuristic model, not a certified forecast. Keep it under 200 words. Output in English and Tamil."
    )
    text_payload = json.dumps({"zones": zones, "exposure": exposure}, ensure_ascii=False)
    try:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content([prompt, text_payload])
            return _extract_text_from_response(response)
        except Exception:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    {"text": prompt},
                    {"text": text_payload},
                ],
            )
            return _extract_text_from_response(response)
    except Exception:
        return None


def build_advisory_text(zones: list[dict[str, str]], exposure: dict[str, Any]) -> dict[str, str]:
    def task():
        live_output = _call_live_gemini_advisory(zones, exposure)
        if live_output and live_output.strip():
            content = live_output.strip()
            english = content.split("English:", 1)[1].split("Tamil:", 1)[0].strip() if "English:" in content and "Tamil:" in content else content
            tamil = content.split("Tamil:", 1)[1].strip() if "Tamil:" in content else CACHED_ADVISORY_TA
            return {
                "advisory_en": english,
                "advisory_ta": tamil,
                "confidence_note": CACHED_CONFIDENCE_NOTE,
            }
        return {
            "advisory_en": CACHED_ADVISORY_EN,
            "advisory_ta": CACHED_ADVISORY_TA,
            "confidence_note": CACHED_CONFIDENCE_NOTE,
        }

    return call_with_timeout(task, timeout=8, cached_fallback={
        "advisory_en": CACHED_ADVISORY_EN,
        "advisory_ta": CACHED_ADVISORY_TA,
        "confidence_note": CACHED_CONFIDENCE_NOTE,
    })


def fetch_forecast_payload(cyclone_id: str | None = None) -> dict[str, Any]:
    payload = os.getenv("FORECAST_PAYLOAD_JSON")
    if payload:
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            pass
    forecast_url = os.getenv("FORECAST_API_URL")
    if forecast_url:
        try:
            import requests
            response = requests.get(forecast_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("exposure"):
                return data
        except Exception:
            pass
    mock_copy = json.loads(json.dumps(MOCK_FORECAST))
    if cyclone_id and cyclone_id != "demo":
        mock_copy["cyclone_name"] = cyclone_id
    return mock_copy


def build_advisory_response(cyclone_id: str = "demo") -> dict[str, Any]:
    forecast = fetch_forecast_payload(cyclone_id)
    exposure = forecast.get("exposure", MOCK_FORECAST["exposure"])
    risk_map = generate_risk_map(seed=7)
    image_dir = Path("tmp") / "risk_maps"
    image_path = render_risk_map_image(risk_map, image_dir / f"{cyclone_id or 'demo'}_risk.png")
    zones = call_risk_zones(image_path, forecast, risk_map)
    advisory = build_advisory_text(zones, exposure)
    return {
        "zones": zones,
        "advisory_en": advisory["advisory_en"],
        "advisory_ta": advisory["advisory_ta"],
        "confidence_note": advisory["confidence_note"],
        "risk_level": compute_risk_level(exposure),
    }
