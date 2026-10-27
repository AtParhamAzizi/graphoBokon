import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_pages import build


class PagesTests(unittest.TestCase):
    def test_build_contains_only_static_assets_and_browser_analyzer(self):
        with tempfile.TemporaryDirectory() as directory:
            site = build(Path(directory))
            html = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn('data-mode="browser"', html)
            self.assertNotIn('src="/', html)
            self.assertTrue((site / ".nojekyll").is_file())
            self.assertTrue((site / "analysis-worker.mjs").is_file())
            self.assertTrue((site / "python/backend/analyzer.py").is_file())
            self.assertFalse((site / "python/backend/main.py").exists())
            self.assertFalse((site / "python/backend/remote.py").exists())
            self.assertFalse((site / "tests").exists())
            manifest = json.loads((site / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn(".py", manifest["extensions"])
            self.assertIn("node_modules", manifest["excluded"])
            demo = json.loads((site / "demo.json").read_text(encoding="utf-8"))
            self.assertEqual(demo["result"]["root"], "demo_project")
            self.assertIn("app/main.py", demo["sources"])
            self.assertGreater(demo["result"]["stats"]["symbols"], 90)
            for node in demo["result"]["nodes"]:
                if node["kind"] == "file":
                    self.assertIn(node["path"], demo["sources"])

    def test_build_can_refresh_generated_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            site = build(Path(directory))
            (site / "index.html").write_text("old build", encoding="utf-8")
            build(site)
            self.assertIn('data-mode="browser"', (site / "index.html").read_text(encoding="utf-8"))
