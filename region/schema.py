from dataclasses import dataclass, field
from pathlib import Path
import yaml

@dataclass
class RegionConfig:
    name: str
    display_name: str
    bbox: tuple[float, float, float, float]   # (west, south, east, north)
    languages: list[str]
    data_dir: Path                             # region-specific data folder
    infra_sources: dict[str, str]              # {"hospitals": "tn_ogd", "substations": "manual_tangedco", ...}
    dispatch_contacts_path: Path
    historical_storms: list[str] = field(default_factory=list)

    @property
    def dem_path(self) -> Path: return self.data_dir / "dem.tif"
    @property
    def rainfall_path(self) -> Path: return self.data_dir / "rainfall.tif"
    @property
    def sar_before_path(self) -> Path: return self.data_dir / "sar_before.tif"
    @property
    def hospitals_path(self) -> Path: return self.data_dir / "hospitals.geojson"
    @property
    def roads_path(self) -> Path: return self.data_dir / "roads.geojson"
    @property
    def substations_path(self) -> Path: return self.data_dir / "substations.geojson"
    @property
    def track_path(self) -> Path: return self.data_dir / "active_track.json"

def load_region(name: str, regions_root: Path = Path("regions")) -> RegionConfig:
    cfg = yaml.safe_load((regions_root / f"{name}.yaml").read_text())
    cfg["data_dir"] = Path(cfg["data_dir"])
    cfg["dispatch_contacts_path"] = Path(cfg["dispatch_contacts_path"])
    cfg["bbox"] = tuple(cfg["bbox"])
    return RegionConfig(**cfg)

def list_regions(regions_root: Path = Path("regions")) -> list[str]:
    return [p.stem for p in regions_root.glob("*.yaml")]