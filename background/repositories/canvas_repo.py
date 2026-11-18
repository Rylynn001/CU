"""画布文档和画布节点生成任务。"""
import json
import uuid
from database import execute_query, get_db


def list_canvases(user_id: int):
    return execute_query(
        'SELECT id, name, updated_at FROM canvas WHERE user_id = %s AND deleted_at IS NULL ORDER BY updated_at DESC, id DESC',
        (user_id,), fetch_all=True,
    ) or []


def get_canvas(canvas_id: int, user_id: int):
    return execute_query(
        'SELECT id, name, document, updated_at FROM canvas WHERE id = %s AND user_id = %s AND deleted_at IS NULL',
        (canvas_id, user_id), fetch_one=True,
    )


def create_canvas(user_id: int, name: str, document: dict):
    return execute_query(
        'INSERT INTO canvas (user_id, name, document) VALUES (%s, %s, %s)',
        (user_id, name, json.dumps(document, ensure_ascii=False)),
    )


def rename_canvas(canvas_id: int, user_id: int, name: str):
    execute_query(
        'UPDATE canvas SET name = %s WHERE id = %s AND user_id = %s AND deleted_at IS NULL',
        (name, canvas_id, user_id),
    )


def save_canvas(canvas_id: int, user_id: int, name: str, document: dict, base_node_ids: list[str]):
    # 保留客户端加载后由助手新增的节点，避免自动保存覆盖正在提交的生成任务。
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT document FROM canvas WHERE id = %s AND user_id = %s AND deleted_at IS NULL FOR UPDATE', (canvas_id, user_id))
        row = cursor.fetchone()
        if not row:
            raise ValueError('画布不存在')
        existing = json.loads(row['document']) if isinstance(row['document'], str) else row['document']
        submitted = {node['id'] for node in document['nodes']}
        known = set(base_node_ids)
        added = {node['id'] for node in existing['nodes'] if node['id'] not in known and node['id'] not in submitted}
        document['nodes'].extend(node for node in existing['nodes'] if node['id'] in added)
        # 助手新建的节点及其入边一起合并，普通编辑仍以客户端文档为准。
        node_ids = {node['id'] for node in document['nodes']}
        edge_ids = {edge['id'] for edge in document['edges']}
        document['edges'].extend(edge for edge in existing['edges']
                                 if edge['target'] in added and edge['source'] in node_ids and edge['id'] not in edge_ids)
        existing_nodes = {node['id']: node for node in existing['nodes']}
        for node in document['nodes']:
            server_data = existing_nodes.get(node['id'], {}).get('data', {})
            if server_data.get('executionId'):
                node['data']['executionId'] = server_data['executionId']
        cursor.execute(
            'UPDATE canvas SET name = %s, document = %s WHERE id = %s',
            (name, json.dumps(document, ensure_ascii=False), canvas_id),
        )
        conn.commit()
    return document


def create_generation(canvas_id: int, user_id: int, media_type: str, parameters: dict,
                      session_id=None, conversation_id=None, node_id=None):
    """在同一事务中保存生成节点和任务归属，然后才允许向供应商提交。"""
    execution_id = str(uuid.uuid4())
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT document FROM canvas WHERE id = %s AND user_id = %s AND deleted_at IS NULL FOR UPDATE', (canvas_id, user_id))
        row = cursor.fetchone()
        if not row:
            raise ValueError('画布不存在')
        document = json.loads(row['document']) if isinstance(row['document'], str) else row['document']
        node_type = f'remote-{media_type}GenerationNode'
        if node_id:
            node = next((item for item in document['nodes'] if item['id'] == node_id), None)
            if not node or node['type'] != node_type:
                raise ValueError('生成节点不存在或类型不匹配')
            cursor.execute("SELECT id FROM workflow_executions WHERE canvas_id = %s AND node_id = %s AND status IN ('running', 'queued', 'submitting') LIMIT 1", (canvas_id, node_id))
            if cursor.fetchone():
                raise ValueError('该节点已有生成任务正在执行')
        else:
            if len(document['nodes']) >= 2000:
                raise ValueError('画布节点数量已达上限')
            node_id = str(uuid.uuid4())
            node = generation_node(document, node_id, media_type)
            document['nodes'].append(node)
            connect_generation_references(document, node, parameters.get('input_asset_ids') or [])
        data = node['data']
        data.update({
            'prompt': parameters['prompt'], 'model': str(parameters['model']),
            'parameters': parameters.get('parameters') or {key: value for key, value in parameters.items() if key not in ('model', 'prompt', 'parameters', 'input_asset_ids', 'type') and value is not None},
            'inputAssetIds': parameters.get('input_asset_ids') or [],
            'executionId': execution_id,
        })
        data.pop('task', None)
        cursor.execute('UPDATE canvas SET document = %s WHERE id = %s', (json.dumps(document, ensure_ascii=False), canvas_id))
        cursor.execute(
            """INSERT INTO workflow_executions (id, canvas_id, node_id, session_id, conversation_id, workflow_definition, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'running')""",
            (execution_id, canvas_id, node_id, session_id, conversation_id, json.dumps({'type': 'txt2video' if media_type == 'video' else 'txt2img', **parameters})),
        )
        conn.commit()
    return execution_id, node_id


def generation_node(document: dict, node_id: str, media_type: str):
    return {
        'id': node_id, 'type': f'remote-{media_type}GenerationNode',
        'position': {'x': max((item['position']['x'] + 360 for item in document['nodes']), default=0), 'y': 0},
        'data': {
            'label': '视频生成' if media_type == 'video' else '图片生成',
            'handles': [
                {'id': 'in', 'type': 'target', 'dataType': ['IMAGE', 'VIDEO', 'STRING'] if media_type == 'video' else ['IMAGE', 'STRING'], 'label': '参考素材、文本输入'},
                {'id': media_type, 'type': 'source', 'dataType': media_type.upper(), 'label': '生成输出'},
            ],
            'outputs': {},
        },
    }


def connect_generation_references(document: dict, target: dict, asset_ids: list[int]):
    """按引用顺序连接每个资产的来源输出，同一输出只连一次。"""
    connected = set()
    for asset_id in asset_ids:
        for source in document['nodes']:
            if source['id'] == target['id']:
                continue
            output = next(((port, value) for port, value in source['data'].get('outputs', {}).items()
                           if isinstance(value.get('value'), dict) and asset_id in value['value'].get('assetIds', [])), None)
            if not output:
                continue
            port, _ = output
            key = (source['id'], port)
            if key not in connected:
                document['edges'].append({
                    'id': str(uuid.uuid4()), 'source': source['id'], 'sourceHandle': port,
                    'target': target['id'], 'targetHandle': 'in', 'type': 'simplebezier',
                })
                connected.add(key)
            break


def get_asset_messages(canvas_id: int, user_id: int):
    """参考资产从画布节点读取，跨窗口仍可复用。"""
    row = get_canvas(canvas_id, user_id)
    if not row:
        return []
    document = json.loads(row['document']) if isinstance(row['document'], str) else row['document']
    messages = []
    for node in document['nodes']:
        data = node['data']
        ids = list(data.get('inputAssetIds', []))
        for output in data.get('outputs', {}).values():
            if isinstance(output.get('value'), dict):
                ids.extend(output['value'].get('assetIds', []))
        messages.append({'message': data.get('prompt') or data.get('label', ''), 'asset_ids': list(dict.fromkeys(ids))})
    rows = execute_query(
        """SELECT e.workflow_definition, a.id AS asset_id FROM workflow_executions e
           JOIN history_assets_rel r ON r.history_id = JSON_UNQUOTE(JSON_EXTRACT(e.result, '$.history_id'))
           JOIN assets a ON a.id = r.asset_id AND a.rfid = %s
           WHERE e.canvas_id = %s""", (user_id, canvas_id), fetch_all=True,
    ) or []
    for item in rows:
        definition = json.loads(item['workflow_definition']) if isinstance(item['workflow_definition'], str) else item['workflow_definition']
        messages.append({'message': definition.get('prompt', ''), 'asset_ids': [item['asset_id']]})
    return messages


def delete_canvas(canvas_id: int, user_id: int):
    execute_query(
        'UPDATE canvas SET deleted_at = CURRENT_TIMESTAMP(3) WHERE id = %s AND user_id = %s AND deleted_at IS NULL',
        (canvas_id, user_id),
    )


def get_history_task(history_id: int, user_id: int):
    """Redis 状态过期后，仍可从数据库恢复生成结果。"""
    rows = execute_query(
        '''SELECT h.id, h.task_id, h.status, h.message, rel.asset_id
           FROM history h LEFT JOIN history_assets_rel rel ON rel.history_id = h.id
           WHERE h.id = %s AND h.user_id = %s AND h.del_flag = 0
           ORDER BY rel.asset_id''',
        (history_id, user_id), fetch_all=True,
    ) or []
    if not rows:
        return None
    return {
        'history_id': rows[0]['id'], 'task_id': rows[0]['task_id'],
        'status': rows[0]['status'], 'message': rows[0]['message'],
        'asset_ids': [row['asset_id'] for row in rows if row['asset_id'] is not None],
    }
