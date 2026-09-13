from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"
    SERVICE = "service"
    GUEST = "guest"


ROLE_DEFAULT_PERMISSIONS: dict[Role, list[str]] = {
    Role.ADMIN: ["upload", "mkdir", "rename", "delete", "invite"],
    Role.USER: ["upload", "mkdir", "rename"],
    Role.SERVICE: ["upload"],
    Role.GUEST: ["upload"],
}


class Invite(BaseModel):
    # Internal representation. `id` is the stable identifier (also the JWT `sub`).
    # `code` holds the plaintext ONLY transiently right after creation/validation;
    # it is never persisted in clear text (only its SHA-256 hash is stored).
    id: str
    code: str
    role: Role
    base_path: str = ""
    permissions: list[str]
    expires_at: Optional[datetime] = None
    max_uses: int = 0
    used_count: int = 0


class InviteCreate(BaseModel):
    role: Role
    base_path: str = ""
    permissions: Optional[list[str]] = None
    # Either an absolute expiry or a relative window in hours (the app sends hours).
    expires_at: Optional[datetime] = None
    expires_in_hours: Optional[int] = None
    max_uses: int = 0


class InviteCreateResponse(BaseModel):
    # Returned ONCE on creation. This is the only time the plaintext code / URL
    # leaves the server — afterwards only the hash is stored.
    code: str
    url: str
    role: Role
    base_path: str
    permissions: list[str]
    expires_at: Optional[datetime] = None
    max_uses: int = 0


class InviteSummary(BaseModel):
    # Listing shape: no plaintext code, only a short hint for recognition.
    id: str
    code_hint: str
    role: Role
    base_path: str
    permissions: list[str]
    expires_at: Optional[datetime] = None
    max_uses: int = 0
    used_count: int = 0
    created_at: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    base_path: str
    permissions: list[str]


class TokenData(BaseModel):
    # `invite_code` carries the JWT `sub`, which is the invite *id* (uuid),
    # not the plaintext code. Upload sessions are scoped by this stable id.
    invite_code: str
    role: Role
    base_path: str
    permissions: list[str]
