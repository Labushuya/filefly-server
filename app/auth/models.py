from enum import Enum
from datetime import datetime
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
    expires_at: Optional[datetime] = None
    max_uses: int = 0


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    base_path: str
    permissions: list[str]


class TokenData(BaseModel):
    invite_code: str
    role: Role
    base_path: str
    permissions: list[str]
