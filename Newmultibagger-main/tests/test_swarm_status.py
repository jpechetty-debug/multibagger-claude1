from __future__ import annotations

from types import SimpleNamespace

import pytest

from app_routes import swarm


@pytest.mark.asyncio
async def test_swarm_status_runs_npx_without_a_shell(monkeypatch):
    """The command list must execute directly on every supported platform."""
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout='{"status": "ok"}', stderr="")

    monkeypatch.setattr(swarm.subprocess, "run", fake_run)

    assert await swarm.get_swarm_status() == {"status": "ok"}
    assert captured["command"][1:] == ["ruflo", "swarm", "status", "--format", "json"]
    assert "shell" not in captured["kwargs"]
