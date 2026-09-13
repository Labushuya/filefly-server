import importlib

import pytest


@pytest.fixture()
def secure_env(tmp_path, monkeypatch):
    """Point the app at a throwaway DB and a real secret, then reload the modules
    that captured settings/DB_PATH at import time."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-not-the-default-0123456789")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    import app.config as config

    importlib.reload(config)
    import app.db.database as database

    importlib.reload(database)
    import app.auth.service as service

    importlib.reload(service)
    yield service, database, config


def test_fail_fast_on_default_secret(monkeypatch):
    import app.config as config

    importlib.reload(config)
    monkeypatch.setattr(config.settings, "secret_key", config.INSECURE_DEFAULT_SECRET)
    with pytest.raises(RuntimeError):
        config.settings.validate_security()


def test_fail_fast_on_empty_secret(monkeypatch):
    import app.config as config

    importlib.reload(config)
    monkeypatch.setattr(config.settings, "secret_key", "")
    with pytest.raises(RuntimeError):
        config.settings.validate_security()


def test_real_secret_passes(monkeypatch):
    import app.config as config

    importlib.reload(config)
    monkeypatch.setattr(config.settings, "secret_key", "a-real-strong-secret")
    config.settings.validate_security()  # must not raise


@pytest.mark.asyncio
async def test_bootstrap_seeds_once_and_stores_only_hash(secure_env):
    service, database, _ = secure_env
    await database.init_db()
    await service.seed_bootstrap_admin()

    # Exactly one invite, no plaintext code column exists, only a hash.
    db = await database.get_db()
    try:
        async with db.execute("SELECT id, code_hash, role, max_uses FROM invites") as cur:
            rows = await cur.fetchall()
    finally:
        await db.close()
    assert len(rows) == 1
    assert rows[0]["role"] == "admin"
    assert rows[0]["max_uses"] == 1
    assert len(rows[0]["code_hash"]) == 64  # sha256 hex

    # Idempotent: second call adds nothing.
    await service.seed_bootstrap_admin()
    db = await database.get_db()
    try:
        async with db.execute("SELECT COUNT(*) AS n FROM invites") as cur:
            row = await cur.fetchone()
    finally:
        await db.close()
    assert row["n"] == 1


@pytest.mark.asyncio
async def test_create_invite_returns_code_once_and_hashes_it(secure_env):
    service, database, _ = secure_env
    await database.init_db()
    from app.auth.models import InviteCreate, Role

    resp = await service.create_invite(
        InviteCreate(role=Role.GUEST, base_path="photos", max_uses=1)
    )
    assert resp.code  # plaintext returned once
    assert resp.url == f"filefly://invite?code={resp.code}"

    # The plaintext code must NOT be present anywhere in the DB.
    db = await database.get_db()
    try:
        async with db.execute("SELECT code_hash FROM invites") as cur:
            row = await cur.fetchone()
    finally:
        await db.close()
    assert resp.code not in row["code_hash"]
    assert service._hash_code(resp.code) == row["code_hash"]


@pytest.mark.asyncio
async def test_validate_consumes_single_use(secure_env):
    service, database, _ = secure_env
    await database.init_db()
    from fastapi import HTTPException

    from app.auth.models import InviteCreate, Role

    resp = await service.create_invite(
        InviteCreate(role=Role.GUEST, base_path="photos", max_uses=1)
    )
    token, invite = await service.validate_invite(resp.code)
    assert token
    assert invite.role == Role.GUEST

    # Second use is rejected.
    with pytest.raises(HTTPException) as exc:
        await service.validate_invite(resp.code)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_validate_unknown_code_404(secure_env):
    service, database, _ = secure_env
    await database.init_db()
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await service.validate_invite("definitely-not-a-real-code")
    assert exc.value.status_code == 404
