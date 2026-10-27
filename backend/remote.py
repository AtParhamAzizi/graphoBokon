from __future__ import annotations

import io
import os
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

GITHUB_URL = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?(?:/tree/(?P<ref>[^/]+)(?:/(?P<subpath>.+?))?)?/?$")
CACHE_DIR = Path(tempfile.gettempdir()) / "pyarch-repos"
MAX_ZIP_BYTES = 500 * 1024 * 1024


def parse_github_url(text: str):
    match = GITHUB_URL.match(text.strip())
    if not match:
        return None
    info = match.groupdict()
    if any(info[key] in {".", ".."} for key in ("owner", "repo")):
        return None
    return info


def _force_remove(func, path, _):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _clone(url: str, ref: str | None, target: Path) -> bool:
    if not shutil.which("git"):
        return False
    command = ["git", "clone", "--depth", "1", "--single-branch"]
    if ref:
        command += ["--branch", ref]
    result = subprocess.run(command + [url, str(target)], capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        if target.exists():
            shutil.rmtree(target, onerror=_force_remove)
        raise ValueError(f"git clone failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'unknown error'}")
    return True


def _download_zip(owner: str, repo: str, ref: str | None, target: Path) -> None:
    url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{ref or ''}".rstrip("/")
    headers = {"User-Agent": "PyArch-Graph", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as response:
            data = response.read(MAX_ZIP_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise ValueError(f"GitHub download failed ({error.code}). Check the URL, or set GITHUB_TOKEN for private repos.") from error
    except urllib.error.URLError as error:
        raise ValueError(f"Could not reach GitHub: {error.reason}") from error
    if len(data) > MAX_ZIP_BYTES:
        raise ValueError("Repository archive is larger than 500 MB.")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(item.file_size for item in archive.infolist()) > MAX_ZIP_BYTES * 4:
            raise ValueError("Repository is too large to extract.")
        archive.extractall(target)
    inner = [child for child in target.iterdir() if child.is_dir()]
    if len(inner) == 1:
        for child in inner[0].iterdir():
            child.rename(target / child.name)
        inner[0].rmdir()


def fetch_github_repo(text: str, progress=None) -> Path:
    info = parse_github_url(text)
    if not info:
        raise ValueError("Not a GitHub repository URL")
    owner, repo, ref, subpath = info["owner"], info["repo"], info["ref"], info["subpath"]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix="repo-", dir=CACHE_DIR))
    if progress:
        progress(0, 1, f"Downloading {owner}/{repo} from GitHub")
    try:
        if not _clone(f"https://github.com/{owner}/{repo}.git", ref, target):
            _download_zip(owner, repo, ref, target)
        root = (target / subpath).resolve() if subpath else target
        if not root.is_dir() or not root.is_relative_to(target.resolve()):
            raise ValueError(f"Folder '{subpath}' was not found in the repository")
        return root
    except Exception:
        if target.exists():
            shutil.rmtree(target, onerror=_force_remove)
        raise
