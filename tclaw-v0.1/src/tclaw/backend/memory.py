"""Memory index —— SQLite 记忆索引。

管理 MEMORY.md / daily / clippings 等文件的索引，
支持全文搜索和向量搜索（sqlite-vec 可选）。
"""

from __future__ import annotations

import sqlite3
import os
from ..common.settings import MEMORY_INDEX_DB


def init_db(db_path: str | None = None) -> sqlite3.Connection:
    """创建/打开记忆索引数据库，初始化表结构。"""
    path = db_path or MEMORY_INDEX_DB
    os.makedirs(os.path.dirname(path), exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS files (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            path      TEXT NOT NULL UNIQUE,
            mtime     REAL NOT NULL,
            size      INTEGER NOT NULL DEFAULT 0,
            source    TEXT NOT NULL DEFAULT 'memory',
            checksum  TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id    INTEGER NOT NULL REFERENCES files(id),
            path       TEXT NOT NULL,
            source     TEXT NOT NULL DEFAULT 'memory',
            start_line INTEGER NOT NULL DEFAULT 1,
            end_line   INTEGER NOT NULL DEFAULT 1,
            text       TEXT NOT NULL,
            embedding  BLOB,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS embedding_cache (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            text_hash  TEXT NOT NULL UNIQUE,
            model      TEXT NOT NULL DEFAULT 'default',
            embedding  BLOB NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # 全文搜索（FTS5）
    try:
        conn.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
            USING fts5(
                text,
                id UNINDEXED,
                path UNINDEXED,
                source UNINDEXED,
                tokenize='porter unicode61'
            );
        """)
    except Exception:
        pass  # FTS5 可能不可用

    # 索引
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_chunks_file_id ON chunks(file_id);",
        "CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);",
        "CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source);",
        "CREATE INDEX IF NOT EXISTS idx_files_source ON files(source);",
    ]:
        try:
            conn.execute(idx)
        except Exception:
            pass

    conn.commit()
