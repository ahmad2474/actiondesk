import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, cast

import yaml


def resolved_compose(*, local: bool) -> dict[str, Any]:
    command = ["docker", "compose", "--env-file", ".env.example", "-f", "infra/compose.yaml"]
    if local:
        command.extend(["-f", "infra/compose.local.yaml"])
    command.extend(["--profile", "checks", "config", "--format", "json"])
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return cast(dict[str, Any], json.loads(result.stdout))


def test_compose_startup_and_local_exposure() -> None:
    services = yaml.safe_load(Path("infra/compose.yaml").read_text())["services"]
    assert {"web", "api", "worker", "postgres", "redis", "bootstrap"} <= services.keys()
    for name in ("postgres", "redis"):
        assert not services[name].get("ports")
        assert services[name]["healthcheck"]
    assert (
        services["api"]["depends_on"]["bootstrap"]["condition"] == "service_completed_successfully"
    )
    assert services["worker"]["depends_on"]["redis"]["condition"] == "service_healthy"
    for name in ("web", "api"):
        assert all(port.startswith("127.0.0.1:") for port in services[name]["ports"])
    assert "actiondesk_worker.celery_app:celery_app" in services["worker"]["command"]


def test_ci_yaml_and_shell_syntax() -> None:
    workflow = yaml.load(Path(".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    assert workflow["permissions"] == {"contents": "read"}
    assert "pull_request" in workflow["on"]
    for step in workflow["jobs"]["foundation"]["steps"]:
        if "run" in step:
            subprocess.run(["sh", "-n"], input=step["run"], text=True, check=True)


def test_local_mounts_do_not_replace_image_owned_files_in_ci() -> None:
    base = resolved_compose(local=False)["services"]
    local = resolved_compose(local=True)["services"]
    assert all(
        mount["type"] != "bind" for service in base.values() for mount in service.get("volumes", [])
    )
    assert not base["web"].get("volumes")
    web_mounts = {mount["target"]: mount for mount in local["web"]["volumes"]}
    assert web_mounts["/workspace/apps/web"]["type"] == "bind"
    assert web_mounts["/workspace/apps/web"]["source"] == str(Path("apps/web").resolve())
    assert web_mounts["/workspace/apps/web/.next"]["type"] == "volume"
    for name in ("postgres", "redis", "api", "worker", "web"):
        assert base[name]["healthcheck"] == local[name]["healthcheck"]
        assert not base[name]["healthcheck"].get("disable", False)
    assert base["web"].get("user") is None
    assert local["web"].get("user") is None
    users = [
        line.split()[1]
        for line in Path("infra/docker/web.Dockerfile").read_text().splitlines()
        if line.startswith("USER ")
    ]
    assert users[-1] == "node"


def test_ci_compose_selection_propagates_to_recursive_make_targets() -> None:
    workflow = yaml.load(Path(".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    step = next(
        step
        for step in workflow["jobs"]["foundation"]["steps"]
        if step.get("name") == "Run foundation verification"
    )
    arguments = shlex.split(step["run"])
    assert arguments == ["make", "verify", "COMPOSE_FILES=-f infra/compose.yaml"]
    result = subprocess.run(
        ["make", "-n", *arguments[1:]], check=True, capture_output=True, text=True
    )
    runtime_commands = [
        line
        for line in result.stdout.splitlines()
        if line.startswith("docker compose ") and " config " not in line
    ]
    assert runtime_commands
    assert all("compose.local.yaml" not in line for line in runtime_commands)
    assert any(" up --build --wait --wait-timeout 180" in line for line in runtime_commands)
    # Test local defaults independently of the command-line overrides inherited
    # when this test itself is launched by CI's recursive make invocation.
    local_environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES", "COMPOSE_FILES"}
    }
    local = subprocess.run(
        ["make", "-n", "dev"],
        check=True,
        capture_output=True,
        text=True,
        env=local_environment,
    )
    assert "-f infra/compose.yaml -f infra/compose.local.yaml up" in local.stdout
