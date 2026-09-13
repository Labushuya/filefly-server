from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth.models import InviteCreate, Invite, TokenResponse
from app.auth import service
from app.auth.models import TokenData

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> TokenData:
    return service.decode_token(credentials.credentials)


async def require_admin(token: TokenData = Depends(get_current_user)) -> TokenData:
    if "invite" not in token.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return token


@router.post("/invite/validate", response_model=TokenResponse)
async def validate_invite(body: dict):
    code = body.get("code", "")
    if not code:
        raise HTTPException(status_code=400, detail="code required")
    token, invite = await service.validate_invite(code)
    return TokenResponse(
        access_token=token,
        role=invite.role,
        base_path=invite.base_path,
        permissions=invite.permissions,
    )


@router.post("/invite", response_model=Invite)
async def create_invite(data: InviteCreate, _: TokenData = Depends(require_admin)):
    return await service.create_invite(data)


@router.get("/invites", response_model=list[Invite])
async def list_invites(_: TokenData = Depends(require_admin)):
    return await service.list_invites()


@router.delete("/invite/{code}")
async def delete_invite(code: str, _: TokenData = Depends(require_admin)):
    await service.delete_invite(code)
    return {"deleted": code}
