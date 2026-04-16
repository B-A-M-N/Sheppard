import pytest

from src.core.system import SystemManager


@pytest.mark.asyncio
async def test_ensure_local_postgres_ready_skips_remote_targets(monkeypatch):
    sm = SystemManager()
    calls = {"ready": 0, "start": 0}

    async def fake_ready(host, port):
        calls["ready"] += 1
        return False

    async def fake_start():
        calls["start"] += 1

    monkeypatch.setattr(sm, "_postgres_port_ready", fake_ready)
    monkeypatch.setattr(sm, "_start_local_postgres_service", fake_start)

    await sm._ensure_local_postgres_ready("postgresql://sheppard:1234@10.9.66.198:5432/sheppard_v3")

    assert calls == {"ready": 0, "start": 0}


@pytest.mark.asyncio
async def test_ensure_local_postgres_ready_starts_when_local_port_is_down(monkeypatch):
    sm = SystemManager()
    events = []
    ready_results = iter([False, False, True])

    async def fake_ready(host, port):
        events.append(("ready", host, port))
        return next(ready_results)

    async def fake_start():
        events.append(("start",))

    monkeypatch.setattr(sm, "_postgres_port_ready", fake_ready)
    monkeypatch.setattr(sm, "_start_local_postgres_service", fake_start)

    await sm._ensure_local_postgres_ready("postgresql://sheppard:1234@127.0.0.1:5432/sheppard_v3")

    assert events == [
        ("ready", "127.0.0.1", 5432),
        ("start",),
        ("ready", "127.0.0.1", 5432),
        ("ready", "127.0.0.1", 5432),
    ]


@pytest.mark.asyncio
async def test_ensure_local_postgres_ready_raises_when_startup_never_recovers(monkeypatch):
    sm = SystemManager()

    async def fake_ready(host, port):
        return False

    async def fake_start():
        return None

    monkeypatch.setattr(sm, "_postgres_port_ready", fake_ready)
    monkeypatch.setattr(sm, "_start_local_postgres_service", fake_start)

    with pytest.raises(RuntimeError, match="did not become ready"):
        await sm._ensure_local_postgres_ready("postgresql://sheppard:1234@localhost:5432/sheppard_v3")
