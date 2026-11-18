"""助手和手动节点共用的画布生成入口。"""
from api.generation import Txt2ImgRequest, Txt2VideoRequest, txt2img, txt2video
from repositories import canvas_repo
from repositories.workflow_repo import WorkflowRepository
from pathlib import PureWindowsPath


def refresh_tasks(executions, user_id):
    """通过持久化生成历史恢复结果，不依赖会话是否存在或打开。"""
    tasks = []
    for execution in executions:
        definition = execution['workflow_definition']
        task = {
            'media_type': 'video' if definition.get('type') == 'txt2video' else 'image',
            'parameters': {key: value for key, value in definition.items() if key != 'type'},
            **execution['result'], 'execution_id': execution['id'],
            'canvas_id': execution['canvas_id'], 'node_id': execution['node_id'],
            'conversation_id': execution.get('conversation_id'), 'status': execution['status'],
            'error': execution.get('error'),
        }
        if task['status'] in ('queued', 'submitting'):
            task['stage'] = '等待前置步骤' if task['status'] == 'queued' else '正在提交'
        if task['status'] == 'running' and task.get('history_id'):
            rows = WorkflowRepository.get_generation_result(task['history_id'], user_id)
            if rows:
                status = rows[0]['status']
                if status in ('done', 'completed', 'success') and any(row['asset_id'] is not None for row in rows):
                    task['status'] = 'completed'
                    if rows[0].get('message'):
                        task['warning'] = rows[0]['message']
                    task['videos' if task.get('media_type') == 'video' else 'images'] = [
                        {'url': f"/api/api-proxy/output/{PureWindowsPath(row['location']).name}", 'asset_id': row['asset_id']}
                        for row in rows if row['asset_id'] is not None and row['location']
                    ]
                elif status in ('error', 'failed', 'cancelled'):
                    task['status'] = 'failed'
                    task['error'] = rows[0]['message'] or '生成失败'
                else:
                    task['stage'] = status
                if task['status'] != execution['status']:
                    WorkflowRepository.update_execution(execution['id'], status=task['status'], result=task,
                        progress=100 if task['status'] == 'completed' else 0, error=task.get('error'))
        tasks.append(task)
    return tasks


def apply_tasks(document, tasks):
    """文档负责节点布局与输入，执行表负责节点任务与生成输出。"""
    nodes = {node['id']: node for node in document['nodes']}
    for task in tasks:
        node = nodes.get(task['node_id'])
        if not node or node['data'].get('executionId') != task['execution_id']:
            continue
        data = node['data']
        data['task'] = {
            'taskId': task.get('task_id') or task['execution_id'], 'historyId': task.get('history_id') or 0,
            'state': 'pending' if task['status'] in ('running', 'queued', 'submitting') else task['status'],
            'error': task.get('error'),
            'warning': task.get('warning'),
        }
        data['inputAssetIds'] = task['parameters'].get('input_asset_ids') or []
        outputs = task.get('videos') or task.get('images') or []
        if task['status'] == 'completed' and outputs:
            port = 'video' if task.get('media_type') == 'video' else 'image'
            data['outputs'][port] = {'dataType': port.upper(), 'value': {'assetIds': [asset['asset_id'] for asset in outputs]}}
    return document


async def submit_generation(user, canvas_id, media_type, parameters, *, session_id=None,
                            conversation_id=None, node_id=None, model_name=None, on_change=None):
    execution_id, node_id = canvas_repo.create_generation(
        canvas_id, user['user_id'], media_type, parameters, session_id, conversation_id, node_id,
    )
    try:
        if on_change:
            await on_change()
        response = await (txt2video(Txt2VideoRequest(**parameters), user=user) if media_type == 'video'
                          else txt2img(Txt2ImgRequest(**parameters), user=user))
    except BaseException as error:
        WorkflowRepository.update_execution(execution_id, status='failed', error=str(getattr(error, 'detail', error)) or '任务提交已中断')
        raise
    task = {
        'execution_id': execution_id, 'canvas_id': canvas_id, 'node_id': node_id,
        'task_id': response.task_id, 'history_id': response.history_id,
        'status': 'running', 'media_type': media_type, 'model_name': model_name,
        'parameters': parameters,
    }
    WorkflowRepository.update_execution(execution_id, current_node='txt2video' if media_type == 'video' else 'txt2img', result=task)
    if on_change:
        await on_change()
    return task
