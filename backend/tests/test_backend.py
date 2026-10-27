import time
import tempfile
import unittest
from pathlib import Path
from fastapi import HTTPException
from backend.analyzer import analyze_directory
from backend.main import AnalyzeRequest, app, health, jobs, node_details, source, start

class BackendTests(unittest.TestCase):
    def test_default_frontend_exists(self):
        frontend = next(route for route in app.routes if route.name == "frontend")
        self.assertTrue((Path(frontend.app.directory) / "index.html").is_file())

    def test_source_rejects_unindexed_and_oversized_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("print('hello')", encoding="utf-8")
            (root / "secret.env").write_text("SECRET=value", encoding="utf-8")
            job_id = "test-source"
            jobs[job_id] = {"status": "complete", "result": analyze_directory(root)}
            try:
                self.assertEqual(source(job_id, "main.py")["source"], "print('hello')")
                for path, status in (("secret.env", 404), ("../outside.py", 400)):
                    with self.assertRaises(HTTPException) as error:
                        source(job_id, path)
                    self.assertEqual(error.exception.status_code, status)
                (root / "main.py").write_bytes(b"x" * 2_000_001)
                with self.assertRaises(HTTPException) as error:
                    source(job_id, "main.py")
                self.assertEqual(error.exception.status_code, 400)
            finally:
                jobs.pop(job_id, None)

    def test_file_details_include_its_symbol_relationships(self):
        result = analyze_directory("demo_project")
        file = next(node for node in result["nodes"] if node.get("path") == "app/main.py" and node["kind"] == "file")
        job_id = "test-file-details"
        jobs[job_id] = {"status": "complete", "result": result}
        try:
            relationships = node_details(job_id, file["id"])["relationships"]
            self.assertTrue(any(edge["type"] == "CALLS" and edge["source"] != file["id"] for edge in relationships))
            self.assertTrue(any(edge["type"] == "USES_TYPE" for edge in relationships))
        finally:
            jobs.pop(job_id, None)

    def test_health_and_background_job(self):
        self.assertEqual(health(), {"ok": True})
        job_id = start(AnalyzeRequest(path="demo_project"))["job_id"]
        for _ in range(30):
            if jobs[job_id]["status"] in {"complete", "error"}:
                break
            time.sleep(0.05)
        self.assertEqual(jobs[job_id]["status"], "complete")
        expected_files = len(list(Path("demo_project").rglob("*.py")))
        self.assertEqual(jobs[job_id]["result"]["stats"]["python_files"], expected_files)
        self.assertEqual(jobs[job_id]["result"]["stats"]["files"], len([
            node for node in jobs[job_id]["result"]["nodes"] if node["kind"] == "file"
        ]))

if __name__ == "__main__":
    unittest.main()
