import pytest
from unittest.mock import mock_open

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
async def test_ensure_local_postgres_ready_uses_configured_timeout_window(monkeypatch):
    sm = SystemManager()
    attempts = {"count": 0}

    async def fake_ready(host, port):
        attempts["count"] += 1
        return False

    async def fake_start():
        return None

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(sm, "_postgres_port_ready", fake_ready)
    monkeypatch.setattr(sm, "_start_local_postgres_service", fake_start)
    monkeypatch.setattr("src.core.system.asyncio.sleep", fake_sleep)
    monkeypatch.setenv("SHEPPARD_PG_STARTUP_TIMEOUT_S", "60")

    with pytest.raises(RuntimeError, match=r"within 60s \(SHEPPARD_PG_STARTUP_TIMEOUT_S\)"):
        await sm._ensure_local_postgres_ready("postgresql://sheppard:1234@localhost:5432/sheppard_v3")

    assert attempts["count"] == 121


@pytest.mark.asyncio
async def test_ensure_local_postgres_ready_raises_when_startup_never_recovers(monkeypatch):
    sm = SystemManager()

    async def fake_ready(host, port):
        return False

    async def fake_start():
        return None

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(sm, "_postgres_port_ready", fake_ready)
    monkeypatch.setattr(sm, "_start_local_postgres_service", fake_start)
    monkeypatch.setattr("src.core.system.asyncio.sleep", fake_sleep)
    monkeypatch.setenv("SHEPPARD_PG_STARTUP_TIMEOUT_S", "1")

    with pytest.raises(RuntimeError, match=r"within 1s \(SHEPPARD_PG_STARTUP_TIMEOUT_S\)"):
        await sm._ensure_local_postgres_ready("postgresql://sheppard:1234@localhost:5432/sheppard_v3")


@pytest.mark.asyncio
async def test_ensure_local_redis_ready_uses_configured_timeout_window(monkeypatch):
    sm = SystemManager()
    attempts = {"count": 0}

    async def fake_ready(host, port):
        attempts["count"] += 1
        return False

    async def fake_start_local_service(**_kwargs):
        return None

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(sm, "_tcp_port_ready", fake_ready)
    monkeypatch.setattr(sm, "_start_local_service", fake_start_local_service)
    monkeypatch.setattr("src.core.system.asyncio.sleep", fake_sleep)
    monkeypatch.setenv("SHEPPARD_REDIS_STARTUP_TIMEOUT_S", "12")

    with pytest.raises(RuntimeError, match="within 12s"):
        await sm._ensure_local_redis_ready("redis://localhost:6379")

    assert attempts["count"] == 25


@pytest.mark.asyncio
async def test_apply_pending_migrations_raises_on_non_idempotency_errors(monkeypatch):
    sm = SystemManager()

    class FakeConn:
        async def fetchval(self, _query):
            return False

    class _Acquire:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakePool:
        def acquire(self):
            return _Acquire()

    async def fake_execute(_conn, _migration_name, _sql):
        raise Exception("syntax error at or near BROKEN")

    sm.pg_pool = FakePool()
    monkeypatch.setattr(sm, "_execute_migration", fake_execute)
    monkeypatch.setattr("src.core.system.os.path.isdir", lambda _path: True)
    monkeypatch.setattr("src.core.system.os.listdir", lambda _path: ["phase_99_broken.sql"])
    monkeypatch.setattr("builtins.open", mock_open(read_data="select 1;"))

    with pytest.raises(RuntimeError, match=r"Migration failed in phase_99_broken\.sql"):
        await sm._apply_pending_migrations()


@pytest.mark.asyncio
async def test_apply_pending_migrations_continues_on_idempotency_errors(monkeypatch):
    sm = SystemManager()
    executed = []

    class FakeConn:
        async def fetchval(self, _query):
            return False

    class _Acquire:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakePool:
        def acquire(self):
            return _Acquire()

    async def fake_execute(_conn, migration_name, _sql):
        executed.append(migration_name)
        raise Exception("relation already exists")

    sm.pg_pool = FakePool()
    monkeypatch.setattr(sm, "_execute_migration", fake_execute)
    monkeypatch.setattr("src.core.system.os.path.isdir", lambda _path: True)
    monkeypatch.setattr("src.core.system.os.listdir", lambda _path: ["phase_99_existing.sql"])
    monkeypatch.setattr("builtins.open", mock_open(read_data="select 1;"))

    await sm._apply_pending_migrations()

    assert executed == ["phase_99_existing"]
