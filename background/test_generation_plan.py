"""隔离外部模型、数据库和生成服务，验证四步计划及中断恢复。"""
import copy
import json
import unittest
import uuid
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from agents.services.generation_plan import GenerationPlan
from agents.services import plan_scheduler, workflow_tools
from api import generation
from repositories import generation_plan_repo


def four_steps():
    return [
        {'id': 'man', 'label': '男主', 'media_type': 'image', 'prompt': '男主角色图', 'depends_on': [], 'input_asset_ids': []},
        {'id': 'woman', 'label': '女主', 'media_type': 'image', 'prompt': '女主角色图', 'depends_on': [], 'input_asset_ids': []},
        {'id': 'photo', 'label': '合影', 'media_type': 'image', 'prompt': '参考图中的两人合影，保持面部和服装一致', 'depends_on': ['man', 'woman'], 'input_asset_ids': []},
        {'id': 'video', 'label': '合影视频', 'media_type': 'video', 'prompt': '合影中的两人向镜头挥手', 'depends_on': ['photo'], 'input_asset_ids': [], 'duration': 8},
    ]


class PlanDefinitionTest(unittest.TestCase):
    def test_dependencies_reject_cycles_duplicates_and_video_to_image(self):
        for mutation in ('future', 'duplicate', 'video'):
            steps = four_steps()
            if mutation == 'future':
                steps[0]['depends_on'] = ['photo']
            elif mutation == 'duplicate':
                steps[1]['id'] = 'man'
            else:
                steps[0]['media_type'] = 'video'
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                GenerationPlan(steps=steps)

    def test_create_plan_writes_four_nodes_three_edges_and_waiting_executions_atomically(self):
        document = {'nodes': [], 'edges': []}
        steps = four_steps()
        for step in steps:
            step.update(parameters={'model': 5, 'prompt': step['prompt'], 'n': 1}, model_name='测试模型')
        cursor = Mock()
        cursor.fetchone.side_effect = [
            {'document': json.dumps(document)},
            {'parameters': json.dumps({'generation_request': {'plan_id': 'plan-1'}})}, None,
        ]
        conn = Mock()
        conn.cursor.return_value = cursor
        with patch.object(generation_plan_repo, 'get_db', return_value=nullcontext(conn)):
            generation_plan_repo.create_plan('plan-1', 4, 2, 3, 7, steps)
        sql_calls = [call.args for call in cursor.execute.call_args_list]
        saved = next(json.loads(args[1][0]) for args in sql_calls if args[0].startswith('UPDATE canvas'))
        self.assertEqual(len(saved['nodes']), 4)
        self.assertEqual(len(saved['edges']), 3)
        video = saved['nodes'][3]
        self.assertEqual(video['type'], 'remote-videoGenerationNode')
        self.assertEqual(saved['edges'][-1]['target'], video['id'])
        self.assertEqual(len([args for args in sql_calls if 'INSERT INTO workflow_executions' in args[0]]), 4)
        conn.commit.assert_called_once()

    def test_confirming_same_plan_does_not_create_more_nodes(self):
        cursor, conn = Mock(), Mock()
        cursor.fetchone.side_effect = [{'document': '{}'}, {'parameters': '{}'}, {'id': 'plan-1'}]
        conn.cursor.return_value = cursor
        with patch.object(generation_plan_repo, 'get_db', return_value=nullcontext(conn)):
            generation_plan_repo.create_plan('plan-1', 4, 2, 3, 7, four_steps())
        self.assertFalse(any('INSERT' in call.args[0] for call in cursor.execute.call_args_list))


class PlanSchedulerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        steps = four_steps()
        self.executions = {}
        self.histories = {}
        for step in steps:
            step.update(execution_id=str(uuid.uuid4()), node_id=str(uuid.uuid4()), model_name='测试模型')
            step['parameters'] = {'model': 5, 'prompt': step['prompt'], 'input_asset_ids': []}
            if step['media_type'] == 'video':
                step['parameters']['duration'] = 8
            self.executions[step['execution_id']] = {
                'id': step['execution_id'], 'canvas_id': 2, 'node_id': step['node_id'], 'status': 'queued',
                'workflow_definition': {'type': 'txt2video' if step['media_type'] == 'video' else 'txt2img', **step['parameters']},
                'result': {'plan_id': 'plan-1', 'label': step['label'], 'step_id': step['id']},
            }
        self.plan = {'id': 'plan-1', 'canvas_id': 2, 'user_id': 4, 'session_id': 3, 'status': 'running', 'definition': steps}
        self.submissions = []
        self.patches = [
            patch.object(generation_plan_repo, 'get_plan', side_effect=lambda _: copy.deepcopy(self.plan)),
            patch.object(generation_plan_repo, 'plan_lock', side_effect=lambda _: nullcontext(True)),
            patch.object(generation_plan_repo, 'set_status', side_effect=lambda _, status: self.plan.update(status=status)),
            patch.object(plan_scheduler.canvas_repo, 'get_canvas', return_value={'id': 2}),
            patch.object(plan_scheduler.WorkflowRepository, 'get_session_executions', side_effect=lambda _: copy.deepcopy(list(self.executions.values()))),
            patch.object(plan_scheduler.WorkflowRepository, 'update_execution', side_effect=self.update),
            patch.object(plan_scheduler.WorkflowRepository, 'get_generation_result', side_effect=lambda history, _: self.histories.get(history, [])),
            patch.object(plan_scheduler, 'submit_generation_task', side_effect=self.submit),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def update(self, execution_id, **values):
        self.executions[execution_id].update(values)

    async def submit(self, req, user, media_type, *, task_id):
        self.submissions.append((req, user, media_type, task_id))
        return SimpleNamespace(task_id=task_id, history_id=len(self.submissions))

    def finish(self, history_id, asset_id, status='done'):
        self.histories[history_id] = [{'status': status, 'message': '生成失败' if status == 'error' else None,
                                     'asset_id': asset_id, 'location': f'D:/output/{asset_id}.png' if asset_id else None}]

    async def test_four_generations_follow_dependencies_and_pass_real_asset_ids(self):
        await plan_scheduler.advance_plan('plan-1')
        self.assertEqual(len(self.submissions), 2)  # 两个角色独立，不等待对方。
        self.finish(1, 101)
        await plan_scheduler.advance_plan('plan-1')
        self.assertEqual(len(self.submissions), 2)  # 只有男主完成，合影仍等待。
        self.finish(2, 102)
        await plan_scheduler.advance_plan('plan-1')
        self.assertEqual(self.submissions[2][0].input_asset_ids, [101, 102])
        self.finish(3, 103)
        await plan_scheduler.advance_plan('plan-1')
        req, user, kind, _ = self.submissions[3]
        self.assertEqual((kind, req.duration, req.input_asset_ids, user['user_id']), ('video', 8, [103], 4))
        self.finish(4, 104)
        await plan_scheduler.advance_plan('plan-1')
        self.assertEqual(self.plan['status'], 'completed')
        await plan_scheduler.advance_plan('plan-1')
        self.assertEqual(len(self.submissions), 4)

    async def test_failure_stops_descendants_retry_preserves_success_and_uses_new_id(self):
        await plan_scheduler.advance_plan('plan-1')
        first_task_id = self.submissions[0][3]
        self.finish(1, None, 'error')
        self.finish(2, 102)
        await plan_scheduler.advance_plan('plan-1')
        self.assertEqual(self.plan['status'], 'failed')
        self.assertEqual(len(self.submissions), 2)
        plan_scheduler.retry_plan('plan-1', 4, 2)
        await plan_scheduler.advance_plan('plan-1')
        self.assertEqual(len(self.submissions), 3)
        self.assertNotEqual(self.submissions[-1][3], first_task_id)
        woman = self.executions[self.plan['definition'][1]['execution_id']]
        self.assertEqual(woman['status'], 'completed')

    async def test_submission_disconnect_recovers_same_task_id(self):
        seen = []
        async def interrupted(req, user, kind, *, task_id):
            seen.append(task_id)
            raise ConnectionError('Redis 响应中断')
        with patch.object(plan_scheduler, 'submit_generation_task', side_effect=interrupted):
            with self.assertRaises(ConnectionError):
                await plan_scheduler.advance_plan('plan-1')
        await plan_scheduler.advance_plan('plan-1')
        self.assertEqual(self.submissions[0][3], seen[0])

    async def test_another_worker_holding_lock_does_not_submit(self):
        with patch.object(generation_plan_repo, 'plan_lock', return_value=nullcontext(False)):
            await plan_scheduler.advance_plan('plan-1')
        self.assertEqual(self.submissions, [])

    def test_retry_rejects_cross_user_and_canvas(self):
        for user_id, canvas_id in ((5, 2), (4, 9)):
            with self.assertRaises(HTTPException) as caught:
                plan_scheduler.retry_plan('plan-1', user_id, canvas_id)
            self.assertEqual(caught.exception.status_code, 404)


class GenerationSubmissionTest(unittest.IsolatedAsyncioTestCase):
    async def test_confirm_plan_validates_all_steps_before_creating_nodes_and_preserves_eight_seconds(self):
        options = {'media_type': 'plan', 'plan_id': 'plan-1',
                   'image': {'model': 5, 'n': 1, 'aspect_ratio': '1:1', 'quality': 'high'},
                   'video': {'model': 6, 'ratio': '16:9', 'resolution': '720p', 'duration': 5}}
        tools = workflow_tools.WorkflowTools({'user_id': 4}, lambda: 3, options, canvas_id=2)
        models = [{'id': 5, 'name': '图片', 'provider': 'openai', 'type': 'image'},
                  {'id': 6, 'name': '视频', 'provider': 'ark', 'type': 'video'}]
        pending = {'plan_id': 'plan-1', 'steps': four_steps()}
        with patch.object(workflow_tools.provider_repo, 'get_all_models', return_value=models) as catalog, \
             patch.object(generation_plan_repo, 'create_plan') as create, \
             patch.object(workflow_tools, 'session_tasks', return_value=[]):
            await tools.confirm_plan(pending)
        steps = create.call_args.args[-1]
        self.assertEqual(len(steps), 4)
        self.assertEqual(steps[-1]['parameters']['duration'], 8)
        catalog.assert_called_once()

        models[0]['parameters'] = {'references': {'images': {'supported': True, 'max': 1}}}
        tools.model_catalog = models
        with patch.object(generation_plan_repo, 'create_plan') as create:
            with self.assertRaises(HTTPException):
                await tools.confirm_plan(pending)
        create.assert_not_called()

    async def test_recovery_reuses_history_and_preserves_video_parameters(self):
        req = generation.Txt2VideoRequest(model=5, prompt='挥手', duration=8, ratio='16:9', resolution='720p')
        model = {'id': 5, 'name': '测试视频', 'provider': 'ark', 'type': 'video', 'rfid': 6}
        with patch.object(generation.generation_repo, 'get_task_history', return_value={'id': 88, 'status': 'pending'}), \
             patch.object(generation, 'get_redis', return_value=Mock(exists=Mock(return_value=False))), \
             patch.object(generation.generation_repo, 'get_model_info', return_value=model), \
             patch.object(generation.generation_repo, 'save_history') as save, \
             patch('config.get_provider_config_by_rfid', return_value={'api_key': 'test', 'base_url': 'local'}), \
             patch.object(generation, 'enqueue_task') as enqueue:
            result = await generation.submit_generation_task(req, {'user_id': 4}, 'video', task_id='fixed-id')
        self.assertEqual(result.history_id, 88)
        save.assert_not_called()
        self.assertEqual(enqueue.call_args.args[1]['parameters']['duration'], 8)

    async def test_lost_submission_response_does_not_revalidate_or_enqueue_again(self):
        with patch.object(generation.generation_repo, 'get_task_history', return_value={'id': 88, 'status': 'pending'}), \
             patch.object(generation, 'get_redis', return_value=Mock(exists=Mock(return_value=True))), \
             patch.object(generation.generation_repo, 'get_model_info') as model, \
             patch.object(generation, 'enqueue_task') as enqueue:
            result = await generation.submit_generation_task(generation.Txt2ImgRequest(model=5, prompt='角色图'), {'user_id': 4}, 'image', task_id='fixed-id')
        self.assertEqual(result.history_id, 88)
        enqueue.assert_not_called()
        model.assert_not_called()

    async def test_completed_task_is_not_requeued(self):
        with patch.object(generation.generation_repo, 'get_task_history', return_value={'id': 88, 'status': 'done'}), \
             patch.object(generation, 'enqueue_task') as enqueue:
            result = await generation.submit_generation_task(generation.Txt2ImgRequest(model=5, prompt='角色图'), {'user_id': 4}, 'image', task_id='fixed-id')
        self.assertEqual(result.history_id, 88)
        enqueue.assert_not_called()


if __name__ == '__main__':
    unittest.main()
