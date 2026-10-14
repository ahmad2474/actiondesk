"""Run browser acceptance against an isolated API/database and loopback web server."""

import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent


def wait_ready(url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Browser fixture process exited; inspect .local/web-checks logs.")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(0.25)
    raise RuntimeError("Browser fixture readiness timed out.")


def main() -> int:
    compose = [
        "docker",
        "compose",
        "--env-file",
        ".env",
        *shlex.split(
            os.environ.get("COMPOSE_FILES", "-f infra/compose.yaml -f infra/compose.local.yaml")
        ),
    ]
    name = "actiondesk-browser-" + uuid4().hex[:12]
    logs = ROOT / ".local" / "web-checks"
    logs.mkdir(parents=True, exist_ok=True)
    processes: list[subprocess.Popen[bytes]] = []
    # Build before launch; never share a mutable .next directory with a dev server.
    subprocess.run(["npm", "run", "build"], cwd=ROOT, check=True)
    try:
        with (logs / "api.log").open("wb") as api_log, (logs / "web.log").open("wb") as web_log:
            api = subprocess.Popen(
                [
                    *compose,
                    "run",
                    "--rm",
                    "--no-deps",
                    "--name",
                    name,
                    "-p",
                    "127.0.0.1:8010:8010",
                    "api",
                    "uv",
                    "run",
                    "--no-sync",
                    "python",
                    "tests/browser/serve.py",
                ],
                cwd=ROOT,
                stdout=api_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            processes.append(api)
            wait_ready("http://127.0.0.1:8010/health", api)
            environment = {
                **os.environ,
                "ACTIONDESK_API_URL": "http://127.0.0.1:8010",
                "WEB_BASE_URL": "http://127.0.0.1:3100",
                "BROWSER_API_URL": "http://127.0.0.1:8010",
            }
            web = subprocess.Popen(
                [
                    "npm",
                    "run",
                    "start",
                    "--workspace",
                    "@actiondesk/web",
                    "--",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    "3100",
                ],
                cwd=ROOT,
                env=environment,
                stdout=web_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            processes.append(web)
            wait_ready("http://127.0.0.1:3100/login", web)
            return subprocess.run(
                ["npx", "playwright", "test", *sys.argv[1:]], cwd=ROOT, env=environment
            ).returncode
    finally:
        # Stop only our named container, allowing its lifespan to drop its generated database.
        subprocess.run(["docker", "stop", "--time", "10", name], capture_output=True, check=False)
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
