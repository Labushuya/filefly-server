import json
import shutil
import uuid
from pathlib import Path

import aiofiles
from fastapi import HTTPException

from app.auth.models import TokenData
from app.config import settings
from app.db.database import get_db


def _resolve_path(base_path: str, rel_path: str) -> Path:
    """Resolve rel_path against storage_root+base_path, blocking traversal."""
    root = Path(settings.storage_root)
    if base_path:
        allowed = (root / base_path).resolve()
    else:
        allowed = root.resolve()

    target = (allowed / rel_path.lstrip("/")).resolve()

    if not str(target).startswith(str(allowed)):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")

    return target


def _require_permission(token: TokenData, perm: str):
    if perm not in token.permissions:
        raise HTTPException(status_code=403, detail=f"Permission '{perm}' required")


async def list_directory(path: str, token: TokenData) -> list[dict]:
    _require_permission(token, "upload")  # minimum: can read dirs they can upload to
    target = _resolve_path(token.base_path, path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    entries = []
    for entry in sorted(target.iterdir()):
        entries.append(
            {
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else 0,
                "modified": entry.stat().st_mtime,
            }
        )
    return entries


async def init_upload(
    filename: str,
    target_path: str,
    total_size: int,
    chunk_count: int,
    conflict_strategy: str,
    token: TokenData,
) -> str:
    _require_permission(token, "upload")
    _resolve_path(token.base_path, target_path)  # validate path

    upload_id = str(uuid.uuid4())
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO upload_sessions
               (upload_id, filename, target_path, total_size, chunk_count,
                received_chunks, conflict_strategy, owner_code)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                upload_id,
                filename,
                target_path,
                total_size,
                chunk_count,
                "[]",
                conflict_strategy,
                token.invite_code,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    tmp_dir = Path(settings.storage_root) / ".filefly_tmp" / upload_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return upload_id


async def receive_chunk(upload_id: str, chunk_index: int, data: bytes, token: TokenData):
    db = await get_db()
    try:
        async with db.execute(
            "SELECT * FROM upload_sessions WHERE upload_id = ? AND owner_code = ?",
            (upload_id, token.invite_code),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Upload session not found")

        if len(data) > settings.max_chunk_size_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Chunk too large")

        tmp_dir = Path(settings.storage_root) / ".filefly_tmp" / upload_id
        chunk_file = tmp_dir / f"chunk_{chunk_index:05d}"
        async with aiofiles.open(chunk_file, "wb") as f:
            await f.write(data)

        received = json.loads(row["received_chunks"])
        if chunk_index not in received:
            received.append(chunk_index)
        await db.execute(
            "UPDATE upload_sessions SET received_chunks = ? WHERE upload_id = ?",
            (json.dumps(sorted(received)), upload_id),
        )
        await db.commit()
    finally:
        await db.close()

    return {"upload_id": upload_id, "chunk_index": chunk_index, "received": len(received)}


async def complete_upload(upload_id: str, token: TokenData) -> dict:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT * FROM upload_sessions WHERE upload_id = ? AND owner_code = ?",
            (upload_id, token.invite_code),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Upload session not found")

        received = json.loads(row["received_chunks"])
        expected = list(range(row["chunk_count"]))
        if sorted(received) != expected:
            missing = sorted(set(expected) - set(received))
            raise HTTPException(status_code=400, detail=f"Missing chunks: {missing}")

        dest_dir = _resolve_path(token.base_path, row["target_path"])
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / row["filename"]

        strategy = row["conflict_strategy"]
        if dest_file.exists():
            if strategy == "skip":
                _cleanup_tmp(upload_id)
                await db.execute("DELETE FROM upload_sessions WHERE upload_id = ?", (upload_id,))
                await db.commit()
                return {"status": "skipped", "path": str(dest_file)}
            elif strategy == "rename":
                dest_file = _auto_rename(dest_file)
            # overwrite: do nothing, just write

        tmp_dir = Path(settings.storage_root) / ".filefly_tmp" / upload_id
        async with aiofiles.open(dest_file, "wb") as out:
            for i in range(row["chunk_count"]):
                chunk_file = tmp_dir / f"chunk_{i:05d}"
                async with aiofiles.open(chunk_file, "rb") as inp:
                    await out.write(await inp.read())

        _cleanup_tmp(upload_id)
        await db.execute("DELETE FROM upload_sessions WHERE upload_id = ?", (upload_id,))
        await db.commit()

        return {
            "status": "complete",
            "path": str(dest_file.relative_to(Path(settings.storage_root))),
        }
    finally:
        await db.close()


def _auto_rename(path: Path) -> Path:
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _cleanup_tmp(upload_id: str):
    tmp_dir = Path(settings.storage_root) / ".filefly_tmp" / upload_id
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)


async def make_dir(path: str, name: str, token: TokenData) -> dict:
    _require_permission(token, "mkdir")
    target = _resolve_path(token.base_path, path) / name
    target.mkdir(parents=True, exist_ok=True)
    return {"created": str(target.relative_to(Path(settings.storage_root)))}


async def rename_entry(path: str, new_name: str, token: TokenData) -> dict:
    _require_permission(token, "rename")
    target = _resolve_path(token.base_path, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    dest = target.parent / new_name
    target.rename(dest)
    return {"renamed": str(dest.relative_to(Path(settings.storage_root)))}


async def delete_entry(path: str, token: TokenData) -> dict:
    _require_permission(token, "delete")
    target = _resolve_path(token.base_path, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"deleted": path}
