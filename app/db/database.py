import os

import aiosqlite

DB_PATH = os.environ.get("DB_PATH", "filefly.db")


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Invites: the plaintext code is NEVER stored. `id` (uuid) is the stable
        # identifier and the JWT subject; `code_hash` (SHA-256) is what we look up.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS invites (
                id TEXT PRIMARY KEY,
                code_hash TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                base_path TEXT NOT NULL DEFAULT '',
                permissions TEXT NOT NULL DEFAULT '[]',
                expires_at TEXT,
                max_uses INTEGER NOT NULL DEFAULT 0,
                used_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_invites_code_hash ON invites (code_hash)")
        # Upload sessions are scoped by owner_code = the invite id (JWT sub).
        await db.execute("""
            CREATE TABLE IF NOT EXISTS upload_sessions (
                upload_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                target_path TEXT NOT NULL,
                total_size INTEGER NOT NULL,
                chunk_count INTEGER NOT NULL,
                received_chunks TEXT NOT NULL DEFAULT '[]',
                conflict_strategy TEXT NOT NULL DEFAULT 'rename',
                owner_code TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.commit()
