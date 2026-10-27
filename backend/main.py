from __future__ import annotations

import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .analyzer import analyze_directory
from .remote import fetch_github_repo, parse_github_url

app = FastAPI(title="PyArch Graph API", version="1.2")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"], allow_methods=["*"], allow_headers=["*"])
jobs = {}


class AnalyzeRequest(BaseModel):
    path: str
    exclusions: list[str] = Field(default_factory=list)


def run_job(job_id, request):
    jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting analysis"}
    try:
        def progress(index, total, message):
            jobs[job_id].update(progress=round(index / max(total, 1) * 100), message=message)

        path = fetch_github_repo(request.path, progress) if parse_github_url(request.path) else request.path
        result = analyze_directory(path, request.exclusions, progress)
        result["source_url"] = request.path if path != request.path else None
        jobs[job_id].update(status="complete", progress=100, message="Analysis complete", result=result)
    except Exception as error:
        jobs[job_id].update(status="error", progress=100, message=str(error))


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/analyses")
def start(request: AnalyzeRequest):
    if not parse_github_url(request.path):
        path = Path(request.path).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise HTTPException(400, "Enter an existing folder or a GitHub URL like https://github.com/owner/repo")
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "progress": 0, "message": "Queued"}
    threading.Thread(target=run_job, args=(job_id, request), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/analyses/{job_id}")
def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Unknown analysis")
    return jobs[job_id]


@app.get("/api/analyses/{job_id}/nodes/{node_id}")
def node_details(job_id: str, node_id: str):
    job = jobs.get(job_id)
    if not job or job.get("status") != "complete":
        raise HTTPException(404, "Analysis not complete")
    result = job["result"]
    node = next((item for item in result["nodes"] if item["id"] == node_id), None)
    if not node:
        raise HTTPException(404, "Unknown node")
    member_ids = {node_id}
    if node["kind"] == "file":
        member_ids.update(item["id"] for item in result["nodes"] if item.get("file_id") == node_id)
    related = [edge for edge in result["edges"] if edge["source"] in member_ids or edge["target"] in member_ids]
    return {"node": node, "relationships": related}


@app.get("/api/analyses/{job_id}/source")
def source(job_id: str, path: str):
    job = jobs.get(job_id)
    if not job or job.get("status") != "complete":
        raise HTTPException(404, "Analysis not complete")
    root = Path(job["result"]["root"]).resolve()
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(400, "Path is outside the analyzed project")
    if not candidate.is_file():
        raise HTTPException(404, "Source file not found")
    relative = candidate.relative_to(root).as_posix()
    if not any(node.get("kind") == "file" and node.get("path") == relative for node in job["result"]["nodes"]):
        raise HTTPException(404, "Source file was not indexed")
    try:
        with candidate.open("rb") as source_file:
            content = source_file.read(2_000_001)
        if len(content) > 2_000_000 or b"\x00" in content:
            raise HTTPException(400, "Source file is too large or contains binary data")
        return {"path": relative, "source": content.decode("utf-8")}
    except (OSError, UnicodeDecodeError):
        raise HTTPException(400, "Source file cannot be read")


@app.get("/api/analyses/{job_id}/export")
def export(job_id: str):
    job = jobs.get(job_id)
    if not job or job.get("status") != "complete":
        raise HTTPException(404, "Analysis not complete")
    return JSONResponse(job["result"], headers={"Content-Disposition": "attachment; filename=pyarch-analysis.json"})


frontend_dir = Path(__file__).resolve().parent.parent / "frontendlow"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
