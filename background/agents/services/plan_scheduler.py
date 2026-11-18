"""在现有 worker 中推进持久化计划，不依赖聊天连接或页面轮询。"""
import asyncio
import logging
import uuid

from fastapi import HTTPException
from pydantic import ValidationError

from api.generation import Txt2ImgRequest, Txt2VideoRequest, submit_generation_task
from repositories import canvas_repo, generation_plan_repo
from repositories.workflow_repo import WorkflowRepository
from .canvas_tasks import refresh_tasks

logger = logging.getLogger(__name__)


async def advance_plan(plan_id):
    # 调度器周期执行：无依赖步骤可立即提交；依赖步骤等上游 history 完成后再提交。
    with generation_plan_repo.plan_lock(plan_id) as acquired:
        if not acquired:
            return
        plan = generation_plan_repo.get_plan(plan_id)
        if not plan or plan['status'] != 'running':
            return
        if not canvas_repo.get_canvas(plan['canvas_id'], plan['user_id']):
            generation_plan_repo.set_status(plan_id, 'failed')
            return
        tasks = {task['execution_id']: task for task in refresh_tasks(
            WorkflowRepository.get_session_executions(plan['session_id']), plan['user_id'],
        )}
        by_step = {step['id']: tasks[step['execution_id']] for step in plan['definition']}
        for step in plan['definition']:
            task = by_step[step['id']]
            if task['status'] not in ('queued', 'submitting'):
                continue
            dependencies = [by_step[key] for key in step['depends_on']]
            if any(item['status'] == 'failed' for item in dependencies):
                task.update(status='failed', error='前置步骤失败，后续生成已停止')
                WorkflowRepository.update_execution(task['execution_id'], status='failed', error=task['error'])
                continue
            if any(item['status'] != 'completed' for item in dependencies):
                continue
            references = list(dict.fromkeys([
                *step['input_asset_ids'],
                *(asset['asset_id'] for dependency in dependencies
                  for asset in (dependency.get('images') or dependency.get('videos') or [])),
            ]))
            parameters = {**step['parameters'], 'input_asset_ids': references}
            attempt = task.get('attempt', 0)
            task_id = str(uuid.uuid5(uuid.UUID(task['execution_id']), str(attempt)))
            # 先保存固定提交编号，重启后可用同一编号恢复，不再次创建节点和历史。
            WorkflowRepository.update_execution(
                task['execution_id'], status='submitting',
                workflow_definition={'type': 'txt2video' if step['media_type'] == 'video' else 'txt2img', **parameters},
            )
            try:
                schema = Txt2VideoRequest if step['media_type'] == 'video' else Txt2ImgRequest
                response = await submit_generation_task(
                    schema(**parameters), {'user_id': plan['user_id']}, step['media_type'], task_id=task_id,
                )
            except (HTTPException, ValidationError, ValueError) as error:
                task.update(status='failed', error=str(getattr(error, 'detail', error)))
                WorkflowRepository.update_execution(task['execution_id'], status='failed', error=task['error'])
                continue
            # Redis/数据库暂时故障时保留 submitting，下次扫描仍使用相同编号。
            task.update(status='running', task_id=response.task_id, history_id=response.history_id,
                        parameters=parameters, error=None, stage='已进入生成队列')
            WorkflowRepository.update_execution(task['execution_id'], status='running', result=task, error='')
        statuses = {task['status'] for task in by_step.values()}
        if not statuses & {'queued', 'submitting', 'running'}:
            status = 'failed' if 'failed' in statuses else 'completed'
            generation_plan_repo.set_status(plan_id, status)


def retry_plan(plan_id, user_id, canvas_id):
    """只重试失败的步骤；成功结果保留，已停止的依赖步骤重新等待。"""
    with generation_plan_repo.plan_lock(plan_id) as acquired:
        if not acquired:
            raise HTTPException(status_code=409, detail='计划正在更新，请稍后重试')
        plan = generation_plan_repo.get_plan(plan_id)
        if not plan or plan['user_id'] != user_id or plan['canvas_id'] != canvas_id:
            raise HTTPException(status_code=404, detail='任务计划不存在')
        if plan['status'] != 'failed':
            raise HTTPException(status_code=409, detail='计划尚未结束或已重试，请刷新进度')
        executions = {row['id']: row for row in WorkflowRepository.get_session_executions(plan['session_id'])}
        for step in plan['definition']:
            execution = executions[step['execution_id']]
            if execution['status'] != 'failed':
                continue
            previous = execution['result'] or {}
            result = {key: previous[key] for key in ('plan_id', 'step_id', 'label', 'model_name') if key in previous}
            result['attempt'] = previous.get('attempt', 0) + 1
            WorkflowRepository.update_execution(execution['id'], status='queued', result=result, error='', progress=0)
        generation_plan_repo.set_status(plan_id, 'running')


async def plan_scheduler_loop():
    while True:
        try:
            for row in generation_plan_repo.active_plan_ids():
                try:
                    await advance_plan(row['id'])
                except Exception:
                    logger.exception('长任务推进失败 plan_id=%s，下次扫描恢复', row['id'])
        except Exception:
            logger.exception('读取长任务计划失败')
        await asyncio.sleep(3)
