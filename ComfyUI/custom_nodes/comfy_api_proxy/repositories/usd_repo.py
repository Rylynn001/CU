import json
from .database import get_db_connection


def ensure_schema() -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''CREATE TABLE IF NOT EXISTS usd_stages (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                user_id BIGINT NOT NULL,
                project_id BIGINT NOT NULL,
                name VARCHAR(255) NOT NULL,
                root_path TEXT NOT NULL,
                session_path TEXT NULL,
                preview_path TEXT NULL,
                session_state LONGTEXT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'ready',
                error TEXT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_usd_stage_owner (user_id, project_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        conn.commit()


def project_owned(project_id: int, user_id: int) -> bool:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('SELECT 1 FROM projects WHERE id=%s AND user_id=%s AND del_flag=0', (project_id, user_id))
            return cursor.fetchone() is not None


def create_stage(user_id: int, project_id: int, name: str, root_path: str) -> int:
    ensure_schema()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('INSERT INTO usd_stages (user_id,project_id,name,root_path) VALUES (%s,%s,%s,%s)', (user_id, project_id, name, root_path))
            stage_id = cursor.lastrowid
        conn.commit()
        return stage_id


def update_paths(stage_id: int, root_path: str, session_path: str) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('UPDATE usd_stages SET root_path=%s,session_path=%s WHERE id=%s', (root_path, session_path, stage_id))
        conn.commit()


def get_stage(stage_id: int, user_id: int) -> dict | None:
    ensure_schema()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM usd_stages WHERE id=%s AND user_id=%s', (stage_id, user_id))
            return cursor.fetchone()


def list_stages(user_id: int, project_id: int) -> list[dict]:
    ensure_schema()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM usd_stages WHERE user_id=%s AND project_id=%s ORDER BY updated_at DESC', (user_id, project_id))
            return cursor.fetchall()


def save_session(stage_id: int, state: dict, status: str = 'ready', error: str | None = None) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('UPDATE usd_stages SET session_state=%s,status=%s,error=%s WHERE id=%s', (json.dumps(state, ensure_ascii=False), status, error, stage_id))
        conn.commit()


def delete_stage(stage_id: int, user_id: int) -> dict | None:
    stage = get_stage(stage_id, user_id)
    if not stage: return None
    with get_db_connection() as conn:
        with conn.cursor() as cursor: cursor.execute('DELETE FROM usd_stages WHERE id=%s AND user_id=%s', (stage_id, user_id))
        conn.commit()
    return stage
