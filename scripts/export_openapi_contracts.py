from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "contracts" / "http"
GENERATED_SUFFIX = ".openapi.json"

SERVICE_APPS: dict[str, tuple[str, str]] = {
    "auth-service": ("services.auth_service.app", "app"),
    "media-service": ("services.media_service.app", "app"),
    "analysis-service": ("services.analysis_service.app", "app"),
    "search-service": ("services.search_service.app", "app"),
    "insight-service": ("services.insight_service.app", "app"),
    "agent-service": ("agents.agent_service.app", "app"),
}


def _load_app(module_name: str, attr_name: str):
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def _export_contract(service_name: str, module_name: str, attr_name: str) -> Path:
    app = _load_app(module_name, attr_name)
    spec = app.openapi()
    spec.setdefault("info", {})["x-service-name"] = service_name

    output_path = OUTPUT_DIR / f"{service_name}{GENERATED_SUFFIX}"
    output_path.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    # Keep contract export side-effect free: skip DB/bootstrap/model initialization.
    import os

    os.environ["URBAN_INSIGHT_APP_MODE"] = "contract-export"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    expected_files: set[str] = set()

    for service_name, (module_name, attr_name) in SERVICE_APPS.items():
        output_path = _export_contract(service_name, module_name, attr_name)
        expected_files.add(output_path.name)
        print(f"exported {output_path.relative_to(ROOT)}")

    for stale_path in OUTPUT_DIR.glob(f"*{GENERATED_SUFFIX}"):
        if stale_path.name in expected_files:
            continue
        stale_path.unlink()
        print(f"removed stale {stale_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
