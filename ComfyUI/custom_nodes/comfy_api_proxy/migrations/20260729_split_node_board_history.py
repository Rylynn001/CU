"""将 node_board 中混合的面板 2 历史记录拆分为图片和视频两列。"""
import importlib.util
import json
from pathlib import Path

import pymysql


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('comfy_api_proxy_config', ROOT / 'config.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


def has_column(cursor, name: str) -> bool:
    cursor.execute('SHOW COLUMNS FROM node_board LIKE %s', (name,))
    return cursor.fetchone() is not None


def main():
    conn = pymysql.connect(**config.get_db_config(), cursorclass=pymysql.cursors.DictCursor)
    try:
        cursor = conn.cursor()
        if not has_column(cursor, 'panel2_image_history_ids'):
            cursor.execute('ALTER TABLE node_board ADD COLUMN panel2_image_history_ids TEXT NULL')
        if not has_column(cursor, 'panel2_video_history_ids'):
            cursor.execute('ALTER TABLE node_board ADD COLUMN panel2_video_history_ids TEXT NULL')

        if has_column(cursor, 'panel2_history_ids'):
            cursor.execute('SELECT id, panel2_history_ids FROM node_board')
            for board in cursor.fetchall():
                history_ids = json.loads(board['panel2_history_ids'] or '[]')
                if history_ids:
                    placeholders = ','.join(['%s'] * len(history_ids))
                    cursor.execute(
                        f'SELECT id, type FROM history WHERE id IN ({placeholders})',
                        history_ids,
                    )
                    types = {row['id']: row['type'] for row in cursor.fetchall()}
                else:
                    types = {}
                image_ids = [
                    history_id for history_id in history_ids
                    if types.get(history_id) not in ('txt2video', 'img2video')
                ]
                video_ids = [
                    history_id for history_id in history_ids
                    if types.get(history_id) in ('txt2video', 'img2video')
                ]
                cursor.execute(
                    '''UPDATE node_board
                       SET panel2_image_history_ids = %s, panel2_video_history_ids = %s
                       WHERE id = %s''',
                    (json.dumps(image_ids), json.dumps(video_ids), board['id']),
                )
            cursor.execute('ALTER TABLE node_board DROP COLUMN panel2_history_ids')
        conn.commit()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
