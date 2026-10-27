from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
if not PYTHON.exists():
    PYTHON = Path(sys.executable)


def main() -> int:
    backend = subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=ROOT,
    )
    print("")
    print("PyArch Graph is starting")
    print("  App:      http://127.0.0.1:8000")
    print("  Enter a path from this computer, such as demo_project")
    print("  Press Ctrl+C to stop the server")
    print("")
    try:
        time.sleep(2)
        if backend.poll() is None:
            webbrowser.open("http://127.0.0.1:8000")
        while backend.poll() is None:
            time.sleep(1)
        print("Server stopped unexpectedly.")
    except KeyboardInterrupt:
        print("\nStopping PyArch Graph...")
        return 0
    finally:
        if backend.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(backend.pid), "/T", "/F"], capture_output=True)
            else:
                backend.terminate()
        try:
            backend.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend.kill()
            backend.wait()
    return backend.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
