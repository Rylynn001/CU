"""
工作流相关的数据访问层
"""
import json
import uuid
from typing import Dict, Any, List, Optional
from database import get_db, execute_query


class WorkflowRepository:
    """工作流数据访问"""

    @staticmethod
    def create_session(user_id: int, canvas_id: int, intent: Optional[str] = None) -> int:
        """创建工作流会话并返回数据库自动生成的整数编号。"""
        return execute_query(
            """
            INSERT INTO workflow_sessions (user_id, canvas_id, intent, status)
            VALUES (%s, %s, %s, 'collecting')
            """,
            (user_id, canvas_id, intent)
        )

    @staticmethod
    def get_session(session_id: int) -> Optional[Dict[str, Any]]:
        """读取会话；parameters 仅保留待确认请求，执行参数从执行表读取。"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM workflow_sessions WHERE id = %s AND deleted_at IS NULL",
                (session_id,)
            )
            result = cursor.fetchone()

            if result:
                result["parameters"] = json.loads(result["parameters"]) if result["parameters"] else {}
            return result

    @staticmethod
    def update_session(session_id: int, intent: Optional[str] = None,
                      parameters: Optional[Dict[str, Any]] = None,
                      status: Optional[str] = None):
        """更新会话"""
        fields = {'intent': intent, 'parameters': parameters, 'status': status}
        updates = [f'{key} = %s' for key, value in fields.items() if value is not None]
        values = [json.dumps(value) if key == 'parameters' else value
                  for key, value in fields.items() if value is not None]

        if not updates:
            return

        values.append(session_id)

        execute_query(
            f"UPDATE workflow_sessions SET {', '.join(updates)} WHERE id = %s",
            tuple(values)
        )

    @staticmethod
    def add_conversation(session_id: int, role: str, message: str, asset_ids: Optional[List[int]] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> int:
        """写入一条用户或 Agent 消息并返回消息编号。"""
        if metadata:
            return execute_query(
                "INSERT INTO workflow_conversations (session_id, role, message, metadata) VALUES (%s, %s, %s, %s)",
                (session_id, role, message, json.dumps(metadata, ensure_ascii=False)),
            )
        if asset_ids:
            return execute_query(
                "INSERT INTO workflow_conversations (session_id, role, message, asset_ids) VALUES (%s, %s, %s, %s)",
                (session_id, role, message, json.dumps(asset_ids)),
            )
        return execute_query(
            """
            INSERT INTO workflow_conversations (session_id, role, message)
            VALUES (%s, %s, %s)
            """,
            (session_id, role, message)
        )

    @staticmethod
    def get_conversations(session_id: int) -> List[Dict[str, Any]]:
        """按时间顺序读取 workflow_conversations，供下一轮模型恢复上下文。"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, role, message, created_at, asset_ids, metadata
                FROM workflow_conversations
                WHERE session_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,)
            )
            rows = cursor.fetchall()
            for row in rows:
                row["asset_ids"] = json.loads(row["asset_ids"]) if row["asset_ids"] else []
                row["metadata"] = json.loads(row["metadata"]) if row["metadata"] else {}
            return rows

    @staticmethod
    def get_user_sessions(user_id: int, canvas_id: int) -> List[Dict[str, Any]]:
        """只返回当前画布有消息的会话，以首条用户消息作为窗口名称。"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT s.id, s.canvas_id, s.intent, s.status, s.created_at, s.updated_at,
                       (SELECT LEFT(c.message, 80) FROM workflow_conversations c
                        WHERE c.session_id = s.id AND c.role = 'user' ORDER BY c.id LIMIT 1) AS title
                FROM workflow_sessions s
                WHERE s.user_id = %s AND s.canvas_id = %s AND s.deleted_at IS NULL
                  AND EXISTS (SELECT 1 FROM workflow_conversations c WHERE c.session_id = s.id)
                ORDER BY s.updated_at DESC, s.id DESC
                """,
                (user_id, canvas_id)
            )
            return cursor.fetchall()

    @staticmethod
    def soft_delete_session(session_id: int, user_id: int) -> None:
        """将当前用户的会话标记为已删除。"""
        execute_query(
            "UPDATE workflow_sessions SET deleted_at = NOW() WHERE id = %s AND user_id = %s AND deleted_at IS NULL",
            (session_id, user_id),
        )

    @staticmethod
    def get_session_executions(session_id: int) -> List[Dict[str, Any]]:
        """从 workflow_executions 加载会话提交过的任务。

        workflow_definition 保存本次任务参数，result 保存 task_id、history_id 等返回结果；
        对话 Agent 用这些数据避免把已提交任务误当成尚未执行。
        """
        rows = execute_query(
            "SELECT * FROM workflow_executions WHERE session_id = %s ORDER BY started_at ASC, id ASC",
            (session_id,), fetch_all=True
        ) or []
        for row in rows:
            for key in ("workflow_definition", "result"):
                row[key] = json.loads(row[key]) if row[key] else {}
        return rows

    @staticmethod
    def get_canvas_executions(canvas_id: int, user_id: int) -> List[Dict[str, Any]]:
        rows = execute_query(
            """SELECT e.* FROM workflow_executions e JOIN canvas c ON c.id = e.canvas_id
               WHERE e.canvas_id = %s AND c.user_id = %s AND c.deleted_at IS NULL
               ORDER BY e.started_at ASC, e.id ASC""",
            (canvas_id, user_id), fetch_all=True,
        ) or []
        for row in rows:
            for key in ("workflow_definition", "result"):
                row[key] = json.loads(row[key]) if row[key] else {}
        return rows

    @staticmethod
    def get_generation_result(history_id: int, user_id: int):
        """从 history 和关联的 assets 读取最终状态与图片地址。

        history_assets_rel 是 history 与 assets 的关联表；按 user_id 限定所有者，
        避免通过会话任务读取其他用户的生成结果。
        """
        return execute_query(
            """SELECT h.status, h.message, a.id AS asset_id, a.location
               FROM history h
               LEFT JOIN history_assets_rel r ON r.history_id = h.id
               LEFT JOIN assets a ON a.id = r.asset_id AND a.rfid = h.user_id
               WHERE h.id = %s AND h.user_id = %s""",
            (history_id, user_id), fetch_all=True
        ) or []

    @staticmethod
    def update_execution(execution_id: str, current_node: Optional[str] = None,
                        status: Optional[str] = None, progress: Optional[float] = None,
                        result: Optional[Dict[str, Any]] = None, error: Optional[str] = None,
                        workflow_definition: Optional[Dict[str, Any]] = None):
        """更新 workflow_executions 中的执行节点、状态、结果或错误。"""
        fields = {'current_node': current_node, 'status': status, 'progress': progress,
                  'result': result, 'error': error, 'workflow_definition': workflow_definition}
        updates = [f'{key} = %s' for key, value in fields.items() if value is not None]
        values = [json.dumps(value) if key in ('result', 'workflow_definition') else value
                  for key, value in fields.items() if value is not None]

        if status in ("completed", "failed"):
            updates.append("completed_at = NOW()")
        elif status is not None:
            updates.append("completed_at = NULL")

        if not updates:
            return

        values.append(execution_id)

        execute_query(
            f"UPDATE workflow_executions SET {', '.join(updates)} WHERE id = %s",
            tuple(values)
        )

    @staticmethod
    def get_execution(execution_id: str) -> Optional[Dict[str, Any]]:
        """获取执行记录"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM workflow_executions WHERE id = %s",
                (execution_id,)
            )
            result = cursor.fetchone()

            if result:
                if result["workflow_definition"]:
                    result["workflow_definition"] = json.loads(result["workflow_definition"])
                if result["result"]:
                    result["result"] = json.loads(result["result"])

            return result

    @staticmethod
    def create_review(execution_id: str, node_name: str, review_data: Dict[str, Any]) -> str:
        """创建审核任务"""
        review_id = str(uuid.uuid4())

        execute_query(
            """
            INSERT INTO workflow_reviews (id, execution_id, node_name, review_data, status)
            VALUES (%s, %s, %s, %s, 'pending')
            """,
            (review_id, execution_id, node_name, json.dumps(review_data))
        )

        return review_id

    @staticmethod
    def update_review(review_id: str, status: str, feedback: Optional[str] = None):
        """更新审核状态"""
        execute_query(
            """
            UPDATE workflow_reviews
            SET status = %s, feedback = %s, reviewed_at = NOW()
            WHERE id = %s
            """,
            (status, feedback, review_id)
        )

    @staticmethod
    def get_review(review_id: str) -> Optional[Dict[str, Any]]:
        """获取审核任务"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM workflow_reviews WHERE id = %s",
                (review_id,)
            )
            result = cursor.fetchone()

            if result and result["review_data"]:
                result["review_data"] = json.loads(result["review_data"])

            return result

    @staticmethod
    def get_pending_reviews(execution_id: str) -> List[Dict[str, Any]]:
        """获取待审核任务"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM workflow_reviews
                WHERE execution_id = %s AND status = 'pending'
                ORDER BY created_at ASC
                """,
                (execution_id,)
            )
            results = cursor.fetchall()

            for result in results:
                if result["review_data"]:
                    result["review_data"] = json.loads(result["review_data"])

            return results
