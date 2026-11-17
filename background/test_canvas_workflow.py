"""画布归属回归。设置 CANVAS_DB_TESTS=1 时使用开发库，生成服务始终替换为本地返回。"""
import copy
import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from api import canvases, workflow
from api.generation import TaskResponse
from agents.services import canvas_tasks
from database import execute_query
from repositories import canvas_repo
from repositories.workflow_repo import WorkflowRepository


@unittest.skipUnless(os.environ.get('CANVAS_DB_TESTS') == '1', '仅显式启用时访问开发数据库')
class CanvasWorkflowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = {'id': 2147483000, 'user_id': 2147483000}
        self.empty = {'version': 1, 'nodes': [], 'edges': [], 'viewport': {'x': 0, 'y': 0, 'zoom': 1}}
        self.boards = [canvas_repo.create_canvas(self.user['id'], '画布归属测试', self.empty) for _ in range(2)]
        self.canvas_id, self.other_id = self.boards
        self.session = WorkflowRepository.create_session(self.user['id'], self.canvas_id)
        self.conversation = WorkflowRepository.add_conversation(self.session, 'user', '生成一只小猫')

    def tearDown(self):
        ids = tuple(self.boards)
        execute_query('DELETE FROM workflow_executions WHERE canvas_id IN (%s, %s)', ids)
        execute_query('DELETE c FROM workflow_conversations c JOIN workflow_sessions s ON s.id = c.session_id WHERE s.canvas_id IN (%s, %s)', ids)
        execute_query('DELETE FROM workflow_sessions WHERE canvas_id IN (%s, %s)', ids)
        execute_query('DELETE FROM canvas WHERE id IN (%s, %s)', ids)

    async def submit(self, media_type='image', **kwargs):
        parameters = {'prompt': '一只小猫', 'model': 5, 'parameters': {'n': 1} if media_type == 'image' else {'duration': 5}}
        mock = AsyncMock(return_value=TaskResponse(task_id='local-test-task', history_id=123))
        name = 'txt2video' if media_type == 'video' else 'txt2img'
        with patch.object(canvas_tasks, name, mock):
            task = await canvas_tasks.submit_generation(self.user, self.canvas_id, media_type, parameters,
                session_id=self.session, conversation_id=self.conversation, **kwargs)
        return task

    def document(self):
        return canvases.get_canvas(self.canvas_id, self.user)['document']

    async def test_image_and_video_nodes_are_saved_before_provider_submission(self):
        for media_type in ('image', 'video'):
            async def inspect_before_submit(*_args, **_kwargs):
                nodes = self.document()['nodes']
                node = next(node for node in nodes if node['type'] == f'remote-{media_type}GenerationNode')
                self.assertEqual(node['data']['prompt'], '小猫')
                self.assertEqual(node['data']['task']['state'], 'pending')
                return TaskResponse(task_id=f'test-{media_type}', history_id=123)

            name = 'txt2video' if media_type == 'video' else 'txt2img'
            with patch.object(canvas_tasks, name, inspect_before_submit):
                task = await canvas_tasks.submit_generation(self.user, self.canvas_id, media_type, {'prompt': '小猫', 'model': 5}, session_id=self.session)
            self.assertEqual(task['canvas_id'], self.canvas_id)
            self.assertIsNotNone(task['node_id'])
        self.assertEqual(len(self.document()['nodes']), 2)

    async def test_deleted_session_does_not_remove_canvas_results(self):
        task = await self.submit()
        rows = [{'status': 'done', 'message': None, 'asset_id': 777, 'location': r'D:\output\test.png'}]
        with patch.object(WorkflowRepository, 'get_generation_result', return_value=rows):
            completed = self.document()
        WorkflowRepository.soft_delete_session(self.session, self.user['id'])
        self.assertFalse(WorkflowRepository.get_user_sessions(self.user['id'], self.canvas_id))
        restored = self.document()['nodes'][0]
        self.assertEqual(restored['data']['task']['state'], 'completed')
        self.assertEqual(restored['data']['outputs']['image']['value']['assetIds'], [777])
        self.assertEqual(restored['id'], task['node_id'])
        self.assertEqual(restored, completed['nodes'][0])
    async def test_generation_does_not_append_assets_to_conversation(self):
        await self.submit()
        with patch.object(WorkflowRepository, 'get_generation_result', return_value=[
            {'status': 'done', 'message': None, 'asset_id': 777, 'location': 'test.png'},
        ]):
            self.document()
        self.assertEqual(WorkflowRepository.get_conversations(self.session)[0]['asset_ids'], [])

    async def test_session_history_and_access_are_scoped_to_canvas_and_user(self):
        second = WorkflowRepository.create_session(self.user['id'], self.canvas_id)
        WorkflowRepository.add_conversation(second, 'user', '第二个窗口')
        other = WorkflowRepository.create_session(self.user['id'], self.other_id)
        WorkflowRepository.add_conversation(other, 'user', '其他画布窗口')
        sessions = await workflow.get_sessions(self.canvas_id, self.user)
        self.assertEqual({item.id for item in sessions}, {self.session, second})
        self.assertEqual({item.title for item in sessions}, {'生成一只小猫', '第二个窗口'})
        for action in (workflow.get_session_detail, workflow.delete_session):
            with self.assertRaises(HTTPException) as caught:
                await action(self.session, self.other_id, self.user)
            self.assertEqual(caught.exception.status_code, 403)
        with self.assertRaises(HTTPException):
            workflow._load_chat_state(self.session, self.user['id'], self.other_id)
        with self.assertRaises(HTTPException):
            workflow._require_session(self.session, self.user['id'] - 1, self.canvas_id)

    async def test_stale_autosave_preserves_new_agent_nodes_but_allows_deletion(self):
        stale = copy.deepcopy(self.empty)
        task = await self.submit()
        saved = canvas_repo.save_canvas(self.canvas_id, self.user['id'], '自动保存', stale, [])
        self.assertEqual(saved['nodes'][0]['id'], task['node_id'])
        removed = canvas_repo.save_canvas(self.canvas_id, self.user['id'], '删除节点', copy.deepcopy(self.empty), [task['node_id']])
        self.assertEqual(removed['nodes'], [])
        self.assertEqual(self.document()['nodes'], [])

    async def test_submission_failure_remains_on_canvas_and_can_be_retried(self):
        with patch.object(canvas_tasks, 'txt2img', AsyncMock(side_effect=ValueError('测试提交失败'))):
            with self.assertRaises(ValueError):
                await canvas_tasks.submit_generation(self.user, self.canvas_id, 'image', {'prompt': '小猫', 'model': 5})
        node = self.document()['nodes'][0]
        self.assertEqual(node['data']['task']['state'], 'failed')
        self.assertEqual(node['data']['task']['error'], '测试提交失败')
        await self.submit(node_id=node['id'])
        self.assertEqual(len(self.document()['nodes']), 1)
        self.assertEqual(self.document()['nodes'][0]['data']['task']['state'], 'pending')

    async def test_manual_node_can_generate_without_any_session(self):
        task = await self.submit()
        WorkflowRepository.update_execution(task['execution_id'], status='failed')
        with patch.object(canvas_tasks, 'txt2img', AsyncMock(return_value=TaskResponse(task_id='manual-task', history_id=124))):
            result = await canvases.generate_node(self.canvas_id, task['node_id'], canvases.CanvasGeneration(prompt='手动修改后的提示词', model=5), self.user)
        execution = WorkflowRepository.get_execution(result['execution_id'])
        self.assertIsNone(execution['session_id'])
        self.assertEqual(execution['canvas_id'], self.canvas_id)
        self.assertEqual(self.document()['nodes'][0]['data']['prompt'], '手动修改后的提示词')

    async def test_stale_autosave_cannot_replace_new_execution(self):
        task = await self.submit()
        stale = self.document()
        WorkflowRepository.update_execution(task['execution_id'], status='failed')
        retry = await self.submit(node_id=task['node_id'])
        canvas_repo.save_canvas(self.canvas_id, self.user['id'], '自动保存', stale, [task['node_id']])
        self.assertEqual(self.document()['nodes'][0]['data']['executionId'], retry['execution_id'])

    async def test_reference_lookup_uses_canvas_nodes_across_sessions(self):
        await self.submit()
        document = self.document()
        document['nodes'][0]['data']['outputs'] = {'image': {'dataType': 'IMAGE', 'value': {'assetIds': [777]}}}
        canvas_repo.save_canvas(self.canvas_id, self.user['id'], '参考资产', document, [document['nodes'][0]['id']])
        WorkflowRepository.soft_delete_session(self.session, self.user['id'])
        messages = canvas_repo.get_asset_messages(self.canvas_id, self.user['id'])
        self.assertEqual(messages[0]['asset_ids'], [777])
        self.assertEqual(canvas_repo.get_asset_messages(self.other_id, self.user['id']), [])


if __name__ == '__main__':
    unittest.main()
