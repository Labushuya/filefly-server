import hashlib
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.auth.models import (
    ROLE_DEFAULT_PERMISSIONS,
    Invite,
    InviteCreate,
    InviteCreateResponse,
    InviteSummary,
    Role,
    TokenData,
)
from app.config import settings
from app.db.database import get_db

ALGORITHM = "HS256"

logger = logging.getLogger("filefly.auth")

# One-time bootstrap admin lifetime.
BOOTSTRAP_TTL_HOURS = 24


def _hash_code(code: str) -> str:
    """SHA-256 hex digest. Codes have ~72 bits of entropy, so a plain (unsalted)
    cryptographic hash is an adequate lookup key — no per-code salt needed for a
    high-entropy token, and it keeps the lookup a single indexed query."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _make_token(invite: Invite) -> str:
    expire = datetime.now(timezone.utc).timestamp() + settings.jwt_expire_hours * 3600
    payload = {
        # sub is the stable invite id (uuid), never the plaintext code.
        "sub": invite.id,
        "role": invite.role,
        "base_path": invite.base_path,
        "permissions": invite.permissions,
        "exp": int(expire),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return TokenData(
            invite_code=payload["sub"],
            role=Role(payload["role"]),
            base_path=payload["base_path"],
            permissions=payload["permissions"],
        )
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _build_invite_url(code: str) -> str:
    # The server cannot reliably know its own externally-reachable URL (behind
    # Traefik/NAT/Pi-hole DNS), so the deep-link/QR payload carries only the code.
    # The client already knows the server URL (it just authenticated against it)
    # and composes the full filefly://invite?server=...&code=... when sharing.
    return f"filefly://invite?code={code}"


async def validate_invite(code: str) -> tuple[str, Invite]:
    code_hash = _hash_code(code)
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM invites WHERE code_hash = ?", (code_hash,)) as cursor:
            row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Invite not found")

        invite = Invite(
            id=row["id"],
            code=code,
            role=Role(row["role"]),
            base_path=row["base_path"],
            permissions=json.loads(row["permissions"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            max_uses=row["max_uses"],
            used_count=row["used_count"],
        )

        if invite.expires_at and invite.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail="Invite expired")

        if invite.max_uses > 0 and invite.used_count >= invite.max_uses:
            raise HTTPException(status_code=403, detail="Invite exhausted")

        # Atomic increment guarded against the use limit (mitigates TOCTOU races
        # on concurrent validation). If 0 rows change, another request consumed
        # the last use between our read and write.
        cur = await db.execute(
            """UPDATE invites SET used_count = used_count + 1
               WHERE id = ? AND (max_uses = 0 OR used_count < max_uses)""",
            (invite.id,),
        )
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=403, detail="Invite exhausted")

        token = _make_token(invite)
        return token, invite
    finally:
        await db.close()


def _resolve_expiry(data: InviteCreate) -> Optional[datetime]:
    if data.expires_at:
        return data.expires_at
    if data.expires_in_hours and data.expires_in_hours > 0:
        return datetime.now(timezone.utc) + timedelta(hours=data.expires_in_hours)
    return None


async def create_invite(data: InviteCreate) -> InviteCreateResponse:
    permissions = data.permissions or ROLE_DEFAULT_PERMISSIONS[data.role]
    expires_at = _resolve_expiry(data)
    invite_id, code = await _insert_invite(
        role=data.role,
        base_path=data.base_path,
        permissions=permissions,
        expires_at=expires_at,
        max_uses=data.max_uses,
    )
    return InviteCreateResponse(
        code=code,
        url=_build_invite_url(code),
        role=data.role,
        base_path=data.base_path,
        permissions=permissions,
        expires_at=expires_at,
        max_uses=data.max_uses,
    )


async def _insert_invite(
    role: Role,
    base_path: str,
    permissions: list[str],
    expires_at: Optional[datetime],
    max_uses: int,
) -> tuple[str, str]:
    """Insert a fresh invite with a random high-entropy code. Returns (id, code).
    Retries on the (astronomically unlikely) hash collision."""
    db = await get_db()
    try:
        for _ in range(5):
            invite_id = str(uuid.uuid4())
            code = secrets.token_urlsafe(9)  # ~72 bits
            code_hash = _hash_code(code)
            try:
                await db.execute(
                    """INSERT INTO invites
                       (id, code_hash, role, base_path, permissions,
                        expires_at, max_uses, used_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
                    (
                        invite_id,
                        code_hash,
                        role.value if isinstance(role, Role) else role,
                        base_path,
                        json.dumps(permissions),
                        expires_at.isoformat() if expires_at else None,
                        max_uses,
                    ),
                )
                await db.commit()
                return invite_id, code
            except Exception:
                await db.rollback()
                continue
        raise HTTPException(status_code=500, detail="Could not allocate invite code")
    finally:
        await db.close()


async def list_invites() -> list[InviteSummary]:
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM invites ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
        return [
            InviteSummary(
                id=r["id"],
                # Only the last 2 hash chars — enough to disambiguate in a list,
                # useless for guessing the code.
                code_hint=r["code_hash"][-2:],
                role=Role(r["role"]),
                base_path=r["base_path"],
                permissions=json.loads(r["permissions"]),
                expires_at=datetime.fromisoformat(r["expires_at"]) if r["expires_at"] else None,
                max_uses=r["max_uses"],
                used_count=r["used_count"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
    finally:
        await db.close()


async def delete_invite(identifier: str) -> bool:
    """Delete by invite id (preferred) or by code_hash. Never takes a plaintext
    code (the server never has it after creation)."""
    db = await get_db()
    try:
        await db.execute(
            "DELETE FROM invites WHERE id = ? OR code_hash = ?", (identifier, identifier)
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def seed_bootstrap_admin() -> None:
    """On first start (empty invites table) create a single, expiring, one-time
    admin invite and log the plaintext code ONCE. Idempotent: does nothing if any
    invite already exists."""
    db = await get_db()
    try:
        async with db.execute("SELECT COUNT(*) AS n FROM invites") as cursor:
            row = await cursor.fetchone()
        if row["n"] > 0:
            return
    finally:
        await db.close()

    expires_at = datetime.now(timezone.utc) + timedelta(hours=BOOTSTRAP_TTL_HOURS)
    _id, code = await _insert_invite(
        role=Role.ADMIN,
        base_path="",
        permissions=ROLE_DEFAULT_PERMISSIONS[Role.ADMIN],
        expires_at=expires_at,
        max_uses=1,
    )
    line = "=" * 68
    logger.warning(
        "\n%s\n FileFly bootstrap admin invite (shown ONCE, valid %dh, single use):\n"
        "\n     %s\n\n Redeem it in the FileFly app now. It is not recoverable.\n%s",
        line,
        BOOTSTRAP_TTL_HOURS,
        code,
        line,
    )
