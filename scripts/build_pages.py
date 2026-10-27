from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.analyzer import DEFAULT_EXCLUDED, analyze_directory
from backend.language_readers import READERS


def build(destination: Path = ROOT / "_site") -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    assets = ("index.html", "style.css", "app.js", "browser-client.js", "browser-project.mjs", "analysis-worker.mjs")
    for asset in assets:
        shutil.copyfile(ROOT / "frontendlow" / asset, destination / asset)
    index = destination / "index.html"
    index.write_text(index.read_text(encoding="utf-8").replace('data-mode="backend"', 'data-mode="browser"'), encoding="utf-8")
    package = destination / "python" / "backend"
    package.mkdir(parents=True, exist_ok=True)
    for module in ("__init__.py", "analyzer.py", "language_readers.py"):
        shutil.copyfile(ROOT / "backend" / module, package / module)
    manifest = {
        "extensions": sorted({extension for reader in READERS for extension in reader.extensions}),
        "filenames": sorted({name for reader in READERS for name in reader.filenames}),
        "excluded": sorted(DEFAULT_EXCLUDED),
        "maxFiles": 2000,
        "maxBytes": 2_000_000,
        "maxTotalBytes": 30_000_000,
    }
    (destination / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = analyze_directory(ROOT / "demo_project")
    sources = {node["path"]: (ROOT / "demo_project" / node["path"]).read_text(encoding="utf-8") for node in result["nodes"] if node["kind"] == "file"}
    result["root"] = "demo_project"
    (destination / "demo.json").write_text(json.dumps({"result": result, "sources": sources}), encoding="utf-8")
    (destination / ".nojekyll").touch()
    return destination


if __name__ == "__main__":
    print(f"Pages site built in {build()}")
