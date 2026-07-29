"""节点面板（board）数据库操作，软删除版本"""
import json
from datetime import datetime
from .database import get_db_connection


def _parse_ids(value) -> list[int]:
    if isinstance(value, str):
        return json.loads(value)
    return value or []


def _load_pending_tasks(cursor, history_ids: list[int]) -> list[dict]:
    if not history_ids:
        return []
    placeholders = ','.join(['%s'] * len(history_ids))
    cursor.execute(
        f'''SELECT h.id, h.task_id, h.status, h.message, h.prompt, h.payload, input_rel.asset_id
            FROM history h
            LEFT JOIN history_input_assets_rel input_rel ON input_rel.history_id = h.id
            WHERE h.id IN ({placeholders}) AND h.del_flag = 0
            ORDER BY h.id, input_rel.asset_id''',
        history_ids,
    )
    tasks = {}
    for item in cursor.fetchall():
        history_id = item['id']
        if history_id not in tasks:
            try:
                payload = json.loads(item['payload']) if item['payload'] else {}
            except (TypeError, json.JSONDecodeError):
                payload = {}
            tasks[history_id] = {
                'history_id': history_id,
                'task_id': item['task_id'],
                'status': item['status'],
                'message': item['message'],
                'prompt': item['prompt'] or '',
                'payload': payload,
                'input_asset_ids': [],
            }
        if item['asset_id'] is not None:
            tasks[history_id]['input_asset_ids'].append(item['asset_id'])
    return [tasks[history_id] for history_id in history_ids if history_id in tasks]


def list_boards(user_id: int) -> list[dict]:
    """获取用户所有未删除工作区，按更新时间倒序"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT id, name, updated_at
               FROM node_board
               WHERE user_id = %s AND deleted_at IS NULL
               ORDER BY updated_at DESC''',
            (user_id,)
        )
        rows = cursor.fetchall()
    for r in rows:
        if r.get('updated_at'):
            r['updated_at'] = int(r['updated_at'].timestamp() * 1000)
    return rows


def get_board(board_id: int, user_id: int) -> dict | None:
    """获取单个未删除工作区完整数据（含三个面板）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT id, name,
                      panel1_asset_ids, panel2_asset_ids, panel3_asset_ids,
                      panel2_image_history_ids, panel2_video_history_ids,
                      updated_at
               FROM node_board
               WHERE id = %s AND user_id = %s AND deleted_at IS NULL''',
            (board_id, user_id)
        )
        row = cursor.fetchone()
        if not row:
            return None

        for key in (
            'panel1_asset_ids', 'panel2_asset_ids', 'panel3_asset_ids',
            'panel2_image_history_ids', 'panel2_video_history_ids',
        ):
            row[key] = _parse_ids(row[key])

        history_ids = row['panel2_image_history_ids'] + row['panel2_video_history_ids']
        if history_ids:
            placeholders = ','.join(['%s'] * len(history_ids))
            cursor.execute(
                f'''SELECT h.id, h.status, rel.asset_id
                    FROM history h
                    LEFT JOIN history_assets_rel rel ON rel.history_id = h.id
                    WHERE h.id IN ({placeholders}) AND h.del_flag = 0''',
                history_ids,
            )
            history_rows = cursor.fetchall()
            found_ids = {item['id'] for item in history_rows}
            completed_ids = {
                item['id'] for item in history_rows
                if item['status'] in ('done', 'completed', 'success')
            }
            output_ids = [
                item['asset_id'] for item in history_rows
                if item['id'] in completed_ids and item['asset_id'] is not None
            ]
            resolved_ids = completed_ids | (set(history_ids) - found_ids)
            if resolved_ids:
                row['panel2_image_history_ids'] = [
                    history_id for history_id in row['panel2_image_history_ids']
                    if history_id not in resolved_ids
                ]
                row['panel2_video_history_ids'] = [
                    history_id for history_id in row['panel2_video_history_ids']
                    if history_id not in resolved_ids
                ]
                for asset_id in output_ids:
                    if asset_id not in row['panel2_asset_ids']:
                        row['panel2_asset_ids'].append(asset_id)
                cursor.execute(
                    '''UPDATE node_board
                       SET panel2_asset_ids = %s,
                           panel2_image_history_ids = %s,
                           panel2_video_history_ids = %s
                       WHERE id = %s''',
                    (
                        json.dumps(row['panel2_asset_ids']),
                        json.dumps(row['panel2_image_history_ids']),
                        json.dumps(row['panel2_video_history_ids']),
                        board_id,
                    ),
                )
                conn.commit()

        row['panel2_image_pending_tasks'] = _load_pending_tasks(
            cursor, row['panel2_image_history_ids']
        )
        row['panel2_video_pending_tasks'] = _load_pending_tasks(
            cursor, row['panel2_video_history_ids']
        )

    if row.get('updated_at'):
        row['updated_at'] = int(row['updated_at'].timestamp() * 1000)
    return row


def create_board(user_id: int, name: str) -> dict:
    """新建工作区，返回 {id, name, updated_at}"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO node_board (user_id, name) VALUES (%s, %s)',
            (user_id, name)
        )
        conn.commit()
        board_id = cursor.lastrowid
    return {'id': board_id, 'name': name, 'updated_at': 0}


def save_board(board_id: int, user_id: int,
               panel1_ids: list, panel2_ids: list, panel3_ids: list,
               panel2_image_history_ids: list, panel2_video_history_ids: list) -> bool:
    """保存面板数据（仅操作未删除记录），返回是否成功"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''UPDATE node_board
               SET panel1_asset_ids = %s, panel2_asset_ids = %s, panel3_asset_ids = %s,
                   panel2_image_history_ids = %s,
                   panel2_video_history_ids = %s
               WHERE id = %s AND user_id = %s AND deleted_at IS NULL''',
            (
                json.dumps(panel1_ids), json.dumps(panel2_ids), json.dumps(panel3_ids),
                json.dumps(panel2_image_history_ids), json.dumps(panel2_video_history_ids),
                board_id, user_id,
            )
        )
        conn.commit()
        if cursor.rowcount > 0:
            return True

        # MySQL 在提交内容未变化时也返回 rowcount=0，不能当作工作区不存在。
        cursor.execute(
            '''SELECT 1 FROM node_board
               WHERE id = %s AND user_id = %s AND deleted_at IS NULL''',
            (board_id, user_id),
        )
        return cursor.fetchone() is not None


def resolve_panel2_history(history_id: int, output_asset_ids: list[int]) -> None:
    """将已完成的面板2历史任务替换为输出资产。"""
    if not output_asset_ids:
        return
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT id, panel2_asset_ids,
                      panel2_image_history_ids, panel2_video_history_ids
               FROM node_board
               WHERE deleted_at IS NULL
                 AND (panel2_image_history_ids IS NOT NULL OR panel2_video_history_ids IS NOT NULL)'''
        )
        rows = cursor.fetchall()
        changed = False
        for row in rows:
            image_history_ids = _parse_ids(row['panel2_image_history_ids'])
            video_history_ids = _parse_ids(row['panel2_video_history_ids'])
            if history_id not in image_history_ids and history_id not in video_history_ids:
                continue

            asset_ids = _parse_ids(row['panel2_asset_ids'])
            image_history_ids = [item for item in image_history_ids if item != history_id]
            video_history_ids = [item for item in video_history_ids if item != history_id]
            for asset_id in output_asset_ids:
                if asset_id not in asset_ids:
                    asset_ids.append(asset_id)
            cursor.execute(
                '''UPDATE node_board
                   SET panel2_asset_ids = %s,
                       panel2_image_history_ids = %s,
                       panel2_video_history_ids = %s
                   WHERE id = %s''',
                (
                    json.dumps(asset_ids),
                    json.dumps(image_history_ids),
                    json.dumps(video_history_ids),
                    row['id'],
                ),
            )
            changed = True
        if changed:
            conn.commit()


def rename_board(board_id: int, user_id: int, name: str) -> bool:
    """重命名工作区（仅操作未删除记录）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''UPDATE node_board SET name = %s
               WHERE id = %s AND user_id = %s AND deleted_at IS NULL''',
            (name, board_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_board(board_id: int, user_id: int) -> bool:
    """软删除工作区（设置 deleted_at，不实际删除行）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''UPDATE node_board SET deleted_at = %s
               WHERE id = %s AND user_id = %s AND deleted_at IS NULL''',
            (datetime.now(), board_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
