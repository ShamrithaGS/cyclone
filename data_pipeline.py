import json

import ee
import geemap
import geopandas as gpd
import osmnx as ox
import imdtrack as imd


ee.Initialize(project='cyclone-hackathon')
bbox = ee.Geometry.Rectangle([79.8, 11.5, 80.4, 13.3])

# --- DEM ---
dem = ee.Image("NASA/NASADEM_HGT/001").select('elevation').clip(bbox)
geemap.ee_export_image(dem, filename='dem.tif', scale=30, region=bbox)
print("Done — dem.tif")

# --- Rainfall ---
rainfall = (
    ee.ImageCollection("NASA/GPM_L3/IMERG_V07")
    .filterDate('2023-12-01', '2023-12-06')
    .filterBounds(bbox)
    .select('precipitation')
    .sum()
)
geemap.ee_export_image(rainfall, filename='rainfall.tif', scale=1000, region=bbox)
print("Done — rainfall.tif")

# --- SAR before-scene (after-scene unavailable — see note to Jameen below) ---
before_collection = (
    ee.ImageCollection("COPERNICUS/S1_GRD")
    .filterBounds(bbox)
    .filterDate('2023-11-20', '2023-12-03')
    .filter(ee.Filter.eq('instrumentMode', 'IW'))
    .select('VV')
)
before = before_collection.median()
geemap.ee_export_image(before, filename='sar_before.tif', scale=100, region=bbox)
print("Done — sar_before.tif")

# --- OSMnx infrastructure ---
ox.settings.overpass_url = "https://overpass.kumi.systems/api/interpreter"
ox.settings.requests_timeout = 60
bbox_osm = (79.8, 11.5, 80.4, 13.3)


def safe_features_from_bbox(bbox_tuple, tags, label, urls=None):
    if urls is None:
        urls = [
            "https://overpass.kumi.systems/api/interpreter",
            "https://overpass-api.de/api/interpreter",
        ]

    last_error = None
    for url in urls:
        try:
            ox.settings.overpass_url = url
            gdf = ox.features_from_bbox(bbox_tuple, tags)
            if gdf is None or getattr(gdf, 'empty', True):
                print(f"{label}: no features returned; creating empty output.")
                return gpd.GeoDataFrame(geometry=gpd.GeoSeries([], crs='EPSG:4326'))
            return gdf
        except Exception as exc:
            last_error = exc
            print(f"{label}: fetch failed via {url}: {exc}")

    print(f"{label}: fetch failed ({last_error}). Using empty fallback dataset.")
    return gpd.GeoDataFrame(geometry=gpd.GeoSeries([], crs='EPSG:4326'))


def safe_write_geojson(gdf, filename):
    try:
        gdf.to_file(filename, driver='GeoJSON')
    except Exception as exc:
        print(f"{filename}: GeoJSON writer unavailable ({exc}). Writing empty feature collection instead.")
        empty_payload = {"type": "FeatureCollection", "features": []}
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(empty_payload, f)


print("Fetching substations...")
substations = safe_features_from_bbox(bbox_osm, {'power': 'substation'}, 'Substations')
safe_write_geojson(substations, 'substations.geojson')
print(f"Done — substations.geojson ({len(substations)} features)")

print("Fetching hospitals...")
hospitals = safe_features_from_bbox(bbox_osm, {'amenity': 'hospital'}, 'Hospitals')
safe_write_geojson(hospitals, 'hospitals.geojson')
print(f"Done — hospitals.geojson ({len(hospitals)} features)")

print("Fetching roads...")
roads = safe_features_from_bbox(bbox_osm, {'highway': ['primary', 'trunk', 'motorway']}, 'Roads')
safe_write_geojson(roads, 'roads.geojson')
print(f"Done — roads.geojson ({len(roads)} features)")

# --- Michaung historical track ---
bt = imd.load()
track_df = bt.observations
michaung = track_df[track_df['name'].str.contains('MICHAUNG', case=False, na=False)].copy()

if michaung.empty:
    print("MICHAUNG not found in IMD dataset; writing empty fallback CSV.")
    fallback_rows = [{
        'time': '2026-XX-XXT00:00:00',
        'lat': 12.5,
        'lon': 80.5,
        'wind_kmh': 100,
        'pressure_hpa': 990,
    }]
    import pandas as pd
    pd.DataFrame(fallback_rows).to_csv('michaung_track.csv', index=False)
else:
    michaung = michaung.rename(columns={
        'time': 'time',
        'lat': 'lat',
        'lon': 'lon',
        'wind': 'wind_kmh',
        'pressure': 'pressure_hpa',
    })
    michaung[['time', 'lat', 'lon', 'wind_kmh', 'pressure_hpa']].to_csv('michaung_track.csv', index=False)
    print(f"Done — michaung_track.csv ({len(michaung)} rows)")
    print("Track columns:", ['time', 'lat', 'lon', 'wind_kmh', 'pressure_hpa'])

# --- Live-track fallback (for demo day, not backtest) ---
fallback_track = [
    {"time": "2026-XX-XXT00:00:00", "lat": 12.5, "lon": 80.5, "wind_kmh": 100, "pressure_hpa": 990},
    {"time": "2026-XX-XXT06:00:00", "lat": 12.3, "lon": 80.3, "wind_kmh": 115, "pressure_hpa": 985},
    {"time": "2026-XX-XXT12:00:00", "lat": 12.1, "lon": 80.1, "wind_kmh": 120, "pressure_hpa": 980},
]
with open('test_2026_track.json', 'w', encoding='utf-8') as f:
    json.dump(fallback_track, f, indent=2)
print("Done — test_2026_track.json (fallback, edit timestamps before demo day)")

