from pathlib import Path

import yaml


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
    import subprocess

    workflow = yaml.load(Path(".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    assert workflow["permissions"] == {"contents": "read"}
    assert "pull_request" in workflow["on"]
    for step in workflow["jobs"]["foundation"]["steps"]:
        if "run" in step:
            subprocess.run(["sh", "-n"], input=step["run"], text=True, check=True)
