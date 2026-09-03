from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_compose_web_port_is_bound_to_loopback() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert '"127.0.0.1:8000:8000"' in compose