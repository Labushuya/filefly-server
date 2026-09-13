from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional

from app.auth.service import decode_token
from app.auth.models import TokenData
from app.files import service

router = APIRouter(prefix="/files", tags=["files"])
bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> TokenData:
    return decode_token(credentials.credentials)


class UploadInitRequest(BaseModel):
    filename: str
    target_path: str
    total_size: int
    chunk_count: int
    conflict_strategy: str = "rename"  # overwrite | rename | skip


class MkdirRequest(BaseModel):
    path: str
    name: str


class RenameRequest(BaseModel):
    path: str
    new_name: str


class DeleteRequest(BaseModel):
    path: str


@router.get("/list")
async def list_directory(path: str = "", token: TokenData = Depends(get_current_user)):
    return await service.list_directory(path, token)


@router.post("/upload/init")
async def upload_init(body: UploadInitRequest, token: TokenData = Depends(get_current_user)):
    upload_id = await service.init_upload(
        body.filename,
        body.target_path,
        body.total_size,
        body.chunk_count,
        body.conflict_strategy,
        token,
    )
    return {"upload_id": upload_id}


@router.post("/upload/chunk")
async def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
    token: TokenData = Depends(get_current_user),
):
    data = await chunk.read()
    return await service.receive_chunk(upload_id, chunk_index, data, token)


@router.post("/upload/complete")
async def upload_complete(body: dict, token: TokenData = Depends(get_current_user)):
    upload_id = body.get("upload_id")
    if not upload_id:
        raise HTTPException(status_code=400, detail="upload_id required")
    return await service.complete_upload(upload_id, token)


@router.post("/mkdir")
async def mkdir(body: MkdirRequest, token: TokenData = Depends(get_current_user)):
    return await service.make_dir(body.path, body.name, token)


@router.post("/rename")
async def rename(body: RenameRequest, token: TokenData = Depends(get_current_user)):
    return await service.rename_entry(body.path, body.new_name, token)


@router.delete("/delete")
async def delete(body: DeleteRequest, token: TokenData = Depends(get_current_user)):
    return await service.delete_entry(body.path, token)
