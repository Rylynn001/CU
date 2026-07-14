"""制作板状态的持久化。"""
import json

from .database import get_db_connection


def ensure_schema() -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS production_boards (
            board_id VARCHAR(96) NOT NULL PRIMARY KEY,
            state LONGTEXT NOT NULL,
            version BIGINT NOT NULL DEFAULT 1,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS production_board_snapshots (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            board_id VARCHAR(96) NOT NULL,
            name VARCHAR(120) NOT NULL,
            state LONGTEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_production_board_snapshots (board_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        conn.commit()


def get_board(board_id: str) -> dict | None:
    ensure_schema()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT state, version, updated_at FROM production_boards WHERE board_id = %s', (board_id,))
        row = cursor.fetchone()
    if not row:
        return None
    return {'state': json.loads(row['state']), 'version': row['version'], 'updated_at': row['updated_at'].isoformat()}


def save_board(board_id: str, state: dict) -> dict:
    ensure_schema()
    serialized = json.dumps(state, ensure_ascii=False, separators=(',', ':'))
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO production_boards (board_id, state) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE state = VALUES(state), version = version + 1''', (board_id, serialized))
        conn.commit()
        cursor.execute('SELECT version, updated_at FROM production_boards WHERE board_id = %s', (board_id,))
        row = cursor.fetchone()
    return {'version': row['version'], 'updated_at': row['updated_at'].isoformat()}


def list_snapshots(board_id: str) -> list[dict]:
    ensure_schema()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, created_at FROM production_board_snapshots WHERE board_id = %s ORDER BY id DESC LIMIT 20', (board_id,))
        rows = cursor.fetchall()
    return [{**row, 'created_at': row['created_at'].isoformat()} for row in rows]


def create_snapshot(board_id: str, name: str, state: dict) -> dict:
    ensure_schema()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO production_board_snapshots (board_id, name, state) VALUES (%s, %s, %s)', (board_id, name, json.dumps(state, ensure_ascii=False, separators=(',', ':'))))
        conn.commit()
        snapshot_id = cursor.lastrowid
    return {'id': snapshot_id, 'name': name}


def get_snapshot(board_id: str, snapshot_id: int) -> dict | None:
    ensure_schema()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, state, created_at FROM production_board_snapshots WHERE board_id = %s AND id = %s', (board_id, snapshot_id))
        row = cursor.fetchone()
    if not row:
        return None
    return {**row, 'state': json.loads(row['state']), 'created_at': row['created_at'].isoformat()}
