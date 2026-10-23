"""
工作流相关的数据访问层
"""
import json
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from database import get_db, execute_query


class WorkflowRepository:
    """工作流数据访问"""

    @staticmethod
    def create_session(user_id: int, intent: Optional[str] = None,
                      parameters: Optional[Dict[str, Any]] = None) -> str:
        """创建工作流会话"""
        session_id = str(uuid.uuid4())

        execute_query(
            """
            INSERT INTO workflow_sessions (id, user_id, intent, parameters, status)
            VALUES (%s, %s, %s, %s, 'collecting')
            """,
            (session_id, user_id, intent, json.dumps(parameters) if parameters else None)
        )

        return session_id

    @staticmethod
    def get_session(session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM workflow_sessions WHERE id = %s",
                (session_id,)
            )
            result = cursor.fetchone()

            if result:
                result["parameters"] = json.loads(result["parameters"]) if result["parameters"] else {}
            return result

    @staticmethod
    def update_session(session_id: str, intent: Optional[str] = None,
                      parameters: Optional[Dict[str, Any]] = None,
                      status: Optional[str] = None):
        """更新会话"""
        updates = []
        values = []

        if intent is not None:
            updates.append("intent = %s")
            values.append(intent)

        if parameters is not None:
            updates.append("parameters = %s")
            values.append(json.dumps(parameters))

        if status is not None:
            updates.append("status = %s")
            values.append(status)

        if not updates:
            return

        values.append(session_id)

        execute_query(
            f"UPDATE workflow_sessions SET {', '.join(updates)} WHERE id = %s",
            tuple(values)
        )

    @staticmethod
    def add_conversation(session_id: str, role: str, message: str):
        """添加对话记录"""
        execute_query(
            """
            INSERT INTO workflow_conversations (session_id, role, message)
            VALUES (%s, %s, %s)
            """,
            (session_id, role, message)
        )

    @staticmethod
    def get_conversations(session_id: str) -> List[Dict[str, Any]]:
        """获取对话历史"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT role, message, created_at
                FROM workflow_conversations
                WHERE session_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,)
            )
            return cursor.fetchall()

    @staticmethod
    def get_user_sessions(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """获取用户的会话列表（只返回有对话内容的会话）"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT s.id, s.intent, s.status, s.created_at, s.updated_at
                FROM workflow_sessions s
                INNER JOIN workflow_conversations c ON s.id = c.session_id
                WHERE s.user_id = %s
                ORDER BY s.updated_at DESC
                LIMIT %s
                """,
                (user_id, limit)
            )
            return cursor.fetchall()

    @staticmethod
    def create_execution(session_id: str, workflow_definition: Dict[str, Any]) -> str:
        """创建执行记录"""
        execution_id = str(uuid.uuid4())

        execute_query(
            """
            INSERT INTO workflow_executions (id, session_id, workflow_definition, status)
            VALUES (%s, %s, %s, 'running')
            """,
            (execution_id, session_id, json.dumps(workflow_definition))
        )

        return execution_id

    @staticmethod
    def update_execution(execution_id: str, current_node: Optional[str] = None,
                        status: Optional[str] = None, progress: Optional[float] = None,
                        result: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        """更新执行状态"""
        updates = []
        values = []

        if current_node is not None:
            updates.append("current_node = %s")
            values.append(current_node)

        if status is not None:
            updates.append("status = %s")
            values.append(status)

        if progress is not None:
            updates.append("progress = %s")
            values.append(progress)

        if result is not None:
            updates.append("result = %s")
            values.append(json.dumps(result))

        if error is not None:
            updates.append("error = %s")
            values.append(error)

        if status in ("completed", "failed"):
            updates.append("completed_at = NOW()")

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
