from pathlib import Path
from unittest.mock import Mock

from fastapi import BackgroundTasks

from modules import auth


class _Request:
    scope = {"type": "http"}
    query_params = {}


def test_master_api_key_uses_constant_time_comparison(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_API_KEY", "master-secret")
    compare_digest = Mock(return_value=True)
    monkeypatch.setattr(auth.secrets, "compare_digest", compare_digest)

    result = auth.get_api_key(_Request(), BackgroundTasks(), api_key="master-secret")

    assert result == "master-secret"
    compare_digest.assert_called_once_with("master-secret", "master-secret")


def test_docker_context_excludes_environment_files():
    dockerignore = Path(__file__).parents[1] / ".dockerignore"
    patterns = set(dockerignore.read_text(encoding="utf-8").splitlines())

    assert {".env", ".env.local", ".env.production"} <= patterns
