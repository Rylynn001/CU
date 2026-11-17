"""计划、画布节点和执行记录一起落库；调度锁随数据库连接释放。"""
import json
import uuid
from contextlib import contextmanager

from database import execute_query, get_db
from repositories.canvas_repo import generation_node, connect_generation_references


def create_plan(plan_id, user_id, canvas_id, session_id, conversation_id, steps):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT document FROM canvas WHERE id = %s AND user_id = %s AND deleted_at IS NULL FOR UPDATE', (canvas_id, user_id))
        canvas = cursor.fetchone()
        if not canvas:
            raise ValueError('画布不存在')
        cursor.execute('SELECT parameters FROM workflow_sessions WHERE id = %s AND user_id = %s AND canvas_id = %s AND deleted_at IS NULL FOR UPDATE', (session_id, user_id, canvas_id))
        session = cursor.fetchone()
        if not session:
            raise ValueError('会话不属于当前画布')
        cursor.execute('SELECT id FROM workflow_generation_plans WHERE id = %s AND user_id = %s AND session_id = %s', (plan_id, user_id, session_id))
        if cursor.fetchone():
            return
        pending = json.loads(session['parameters'] or '{}').get('generation_request', {})
        if pending.get('plan_id') != plan_id:
            raise ValueError('任务计划已变化或已确认，请刷新会话')
        document = json.loads(canvas['document']) if isinstance(canvas['document'], str) else canvas['document']
        if len(document['nodes']) + len(steps) > 2000:
            raise ValueError('画布节点数量已达上限')
        nodes = {}
        origin_x = max((node['position']['x'] + 360 for node in document['nodes']), default=0)
        levels = {}
        rows = {}
        for step in steps:
            node_id, execution_id = str(uuid.uuid4()), str(uuid.uuid4())
            level = max((levels[key] + 1 for key in step['depends_on']), default=0)
            levels[step['id']] = level
            row = rows.get(level, 0)
            rows[level] = row + 1
            node = generation_node(document, node_id, step['media_type'])
            node['position'] = {'x': origin_x + level * 400, 'y': row * 380}
            parameters = step['parameters']
            node['data'].update({
                'label': step['label'], 'prompt': step['prompt'], 'model': str(parameters['model']),
                'parameters': {key: value for key, value in parameters.items() if key not in ('model', 'prompt', 'input_asset_ids')},
                'inputAssetIds': step['input_asset_ids'], 'executionId': execution_id,
            })
            document['nodes'].append(node)
            connect_generation_references(document, node, step['input_asset_ids'])
            for dependency in step['depends_on']:
                source = nodes[dependency]
                document['edges'].append({
                    'id': str(uuid.uuid4()), 'source': source['id'],
                    'sourceHandle': source['data']['handles'][1]['id'],
                    'target': node_id, 'targetHandle': 'in', 'type': 'simplebezier',
                })
            nodes[step['id']] = node
            step.update(node_id=node_id, execution_id=execution_id)
            result = {'plan_id': plan_id, 'step_id': step['id'], 'label': step['label'], 'model_name': step['model_name']}
            definition = {'type': 'txt2video' if step['media_type'] == 'video' else 'txt2img', **parameters}
            cursor.execute(
                """INSERT INTO workflow_executions
                   (id, canvas_id, node_id, session_id, conversation_id, workflow_definition, result, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued')""",
                (execution_id, canvas_id, node_id, session_id, conversation_id, json.dumps(definition), json.dumps(result, ensure_ascii=False)),
            )
        cursor.execute('UPDATE canvas SET document = %s WHERE id = %s', (json.dumps(document, ensure_ascii=False), canvas_id))
        cursor.execute('INSERT INTO workflow_generation_plans (id, user_id, canvas_id, session_id, definition) VALUES (%s, %s, %s, %s, %s)',
                       (plan_id, user_id, canvas_id, session_id, json.dumps(steps, ensure_ascii=False)))
        cursor.execute("UPDATE workflow_sessions SET parameters = %s, status = 'executing' WHERE id = %s", ('{}', session_id))
        conn.commit()


def get_plan(plan_id):
    row = execute_query('SELECT * FROM workflow_generation_plans WHERE id = %s', (plan_id,), fetch_one=True)
    if row:
        row['definition'] = json.loads(row['definition']) if isinstance(row['definition'], str) else row['definition']
    return row


def active_plan_ids():
    return execute_query("SELECT id FROM workflow_generation_plans WHERE status = 'running' ORDER BY created_at", fetch_all=True) or []


@contextmanager
def plan_lock(plan_id):
    # 多个服务/worker 实例不会同时推进同一计划；进程退出后锁自动释放。
    with get_db() as conn:
        cursor = conn.cursor()
        name = f'generation-plan:{plan_id}'
        cursor.execute('SELECT GET_LOCK(%s, 0) AS acquired', (name,))
        acquired = bool(cursor.fetchone()['acquired'])
        try:
            yield acquired
        finally:
            if acquired:
                cursor.execute('SELECT RELEASE_LOCK(%s)', (name,))


def set_status(plan_id, status):
    execute_query('UPDATE workflow_generation_plans SET status = %s WHERE id = %s', (status, plan_id))
