import json
import secrets
from datetime import datetime, timezone
from typing import Optional

from jose import jwt, JWTError
from fastapi import HTTPException, status

from app.config import settings
from app.auth.models import Invite, InviteCreate, Role, ROLE_DEFAULT_PERMISSIONS, TokenData
from app.db.database import get_db

ALGORITHM = "HS256"


def _make_token(invite: Invite) -> str:
    expire = datetime.now(timezone.utc).timestamp() + settings.jwt_expire_hours * 3600
    payload = {
        "sub": invite.code,
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


async def validate_invite(code: str) -> tuple[str, Invite]:
    db = await get_db()
    try:
        # Admin bootstrap
        if code == settings.admin_invite_code:
            invite = Invite(
                code=code,
                role=Role.ADMIN,
                base_path="",
                permissions=ROLE_DEFAULT_PERMISSIONS[Role.ADMIN],
            )
            token = _make_token(invite)
            return token, invite

        async with db.execute("SELECT * FROM invites WHERE code = ?", (code,)) as cursor:
            row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Invite not found")

        invite = Invite(
            code=row["code"],
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

        await db.execute(
            "UPDATE invites SET used_count = used_count + 1 WHERE code = ?", (code,)
        )
        await db.commit()

        token = _make_token(invite)
        return token, invite
    finally:
        await db.close()


async def create_invite(data: InviteCreate) -> Invite:
    code = secrets.token_urlsafe(6)[:8]
    permissions = data.permissions or ROLE_DEFAULT_PERMISSIONS[data.role]
    invite = Invite(
        code=code,
        role=data.role,
        base_path=data.base_path,
        permissions=permissions,
        expires_at=data.expires_at,
        max_uses=data.max_uses,
        used_count=0,
    )
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO invites (code, role, base_path, permissions, expires_at, max_uses, used_count)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                invite.code,
                invite.role,
                invite.base_path,
                json.dumps(invite.permissions),
                invite.expires_at.isoformat() if invite.expires_at else None,
                invite.max_uses,
                invite.used_count,
            ),
        )
        await db.commit()
    finally:
        await db.close()
    return invite


async def list_invites() -> list[Invite]:
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM invites ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
        return [
            Invite(
                code=r["code"],
                role=Role(r["role"]),
                base_path=r["base_path"],
                permissions=json.loads(r["permissions"]),
                expires_at=datetime.fromisoformat(r["expires_at"]) if r["expires_at"] else None,
                max_uses=r["max_uses"],
                used_count=r["used_count"],
            )
            for r in rows
        ]
    finally:
        await db.close()


async def delete_invite(code: str) -> bool:
    db = await get_db()
    try:
        await db.execute("DELETE FROM invites WHERE code = ?", (code,))
        await db.commit()
        return True
    finally:
        await db.close()
