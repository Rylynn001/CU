"""提示词与长任务回归测试：替换模型、数据库和生成工具，不发外网、不消耗额度。"""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from PIL import Image

from api import workflow as api
from agents.graph.subgraphs.prompt_enhance import llm_enhance_node
from agents.graph.utils.prompt_validation import PromptEnhancementResult, validate_final_prompt
from agents.services.generation_plan import GenerationPlan
from agents.services.chat_assets import node_reference_images
from agents.skill_agent import SkillManager


def response(data):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(data, ensure_ascii=False)))], usage=None)


def client_for(*results):
    create = AsyncMock(side_effect=[response(result) for result in results])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def ready(prompt):
    return {'status': 'ready', 'prompt': prompt}


def question(text):
    return {'status': 'needs_clarification', 'clarification_type': 'content', 'reply': text}


def fantasy_plan():
    """用户原始场景：三张角色图 → 打斗合照 → 8 秒视频。"""
    steps = []
    for index, label in enumerate(('天使', '恶魔', '精灵', '打斗合照', '8秒视频'), 1):
        steps.append({'id': f's{index}', 'label': label, 'media_type': 'video' if index == 5 else 'image',
                      'prompt': label, 'depends_on': ['s1', 's2', 's3'] if index == 4 else ['s4'] if index == 5 else [],
                      'input_asset_ids': []})
    steps[-1]['duration'] = 8
    return {'intent': 'generation_plan', 'steps': steps}


class SelectionTools:
    """模拟参数面板工具，仅记录请求；测试中不允许提交实际生成。"""
    def __init__(self, *args, **kwargs):
        self.asset_ids = []
        self.allowed_asset_ids = set()
        self.pending_generation = None
        self.calls = []

    async def discover_and_execute(self, name, arguments):
        self.calls.append((name, deepcopy(arguments)))
        if name == 'generation_plan':
            plan = GenerationPlan.model_validate(arguments)
            self.pending_generation = {'media_type': 'plan', 'plan_id': 'test-plan', 'prompt': '计划',
                                       'steps': plan.model_dump(exclude_none=True)['steps'], 'models_by_type': {}}
        else:
            self.pending_generation = {'media_type': 'video' if name == 'txt2video' else 'image',
                                       'prompt': arguments['prompt'], 'models': []}
        return {'selection_required': self.pending_generation}


class PromptValidationTest(unittest.TestCase):
    def test_questions_and_acknowledgments_are_not_prompts(self):
        for text in ('优化哪个模型的提示词？', '“优化哪个模型的提示词？”', '请提供原始提示词', '你想要什么风格？', '好的', '是否需要生成视频？', '   '):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_final_prompt(text)

    def test_quoted_dialogue_and_scene_questions_are_valid(self):
        for text in ('精灵站在两人之间说：“你想要什么？”天使收起翅膀。',
                     '画面中的标牌显示“优化哪个模型的提示词？”，镜头缓缓拉远。',
                     '天使与恶魔对峙。精灵问：“请告诉我发生了什么？”',
                     '雨夜街道，演员低头沉思，字幕为“为什么？”'):
            self.assertEqual(validate_final_prompt(text), text)

    def test_protocol_disallows_mixed_or_unknown_fields(self):
        for result in ({'status': 'ready', 'prompt': '天使站在云端', 'reply': '请确认'},
                       {'status': 'needs_clarification', 'reply': '请提供参考图', 'prompt': '一张图', 'clarification_type': 'reference'},
                       {'status': 'ready', 'prompt': '天使站在云端', 'unexpected': True},
                       {'status': 'reply', 'reply': '优化哪个模型？'}):
            with self.subTest(result=result), self.assertRaises(ValueError):
                PromptEnhancementResult.model_validate(result)


class EnhancementTest(unittest.IsolatedAsyncioTestCase):
    async def test_model_question_is_corrected_once_even_when_mislabeled_ready(self):
        client = client_for(ready('优化哪个模型的提示词？'), ready('天使与恶魔打斗，精灵在中间劝架，连续8秒。'))
        retry = AsyncMock()
        result = await llm_enhance_node({'messages': [{'role': 'user', 'content': '优化并生成视频'}]}, client, on_retry=retry)
        self.assertIn('enhanced_prompt', result)
        self.assertEqual(client.chat.completions.create.await_count, 2)
        retry.assert_awaited_once()

    async def test_parameter_question_is_corrected_instead_of_asking_user(self):
        for kind in ('content', 'generation_parameters'):
            client = client_for({'status': 'needs_clarification', 'clarification_type': kind, 'reply': '使用哪个模型？'}, ready('精灵在森林中行走。'))
            result = await llm_enhance_node({'user_prompt': '精灵视频'}, client)
            self.assertIn('enhanced_prompt', result)
            self.assertEqual(client.chat.completions.create.await_count, 2)

    async def test_genuine_question_is_preserved_without_retry(self):
        client = client_for(question('请提供要优化的原始提示词。'))
        result = await llm_enhance_node({'user_prompt': '优化并生成视频'}, client)
        self.assertEqual(result['clarification']['reply'], '请提供要优化的原始提示词。')
        self.assertNotIn('enhanced_prompt', result)
        self.assertEqual(client.chat.completions.create.await_count, 1)

    async def test_reference_question_can_describe_a_physical_model(self):
        result = await llm_enhance_node({'user_prompt': '使用玩具参考图'}, client_for(
            {'status': 'needs_clarification', 'clarification_type': 'reference', 'reply': '请上传提到的模型玩具参考图片。'},
        ))
        self.assertIn('clarification', result)

    async def test_twice_invalid_or_network_error_never_returns_prompt(self):
        client = client_for(ready('请提供原始提示词'), ready('优化哪个模型的提示词？'))
        result = await llm_enhance_node({'user_prompt': '生成视频'}, client)
        self.assertIn('error', result)
        self.assertNotIn('enhanced_prompt', result)
        self.assertEqual(client.chat.completions.create.await_count, 2)
        client.chat.completions.create = AsyncMock(side_effect=RuntimeError('测试服务中断'))
        self.assertIn('error', await llm_enhance_node({'user_prompt': '生成视频'}, client))
        self.assertEqual(client.chat.completions.create.await_count, 1)

    async def test_empty_provider_result_is_corrected_without_losing_draft(self):
        client = client_for()
        client.chat.completions.create = AsyncMock(side_effect=[SimpleNamespace(choices=[], usage=None), response(ready('精灵穿过森林。'))])
        result = await llm_enhance_node({'user_prompt': '精灵视频'}, client)
        self.assertEqual(result['enhanced_prompt'], '精灵穿过森林。')


class GenerationApiTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # 用同一份内存会话模拟落库和重新加载，覆盖跨请求恢复，而不只测单个函数。
        self.session = {'id': 80, 'user_id': 4, 'canvas_id': 66, 'parameters': {}, 'status': 'collecting', 'intent': None}
        self.messages = []
        self.repo = Mock()
        self.repo.create_session.return_value = 80
        self.repo.get_session.side_effect = lambda _: deepcopy(self.session)
        self.repo.get_conversations.side_effect = lambda _: deepcopy(self.messages)
        self.repo.update_session.side_effect = lambda _, **fields: self.session.update(deepcopy(fields))

        def add_message(_, role, text, **kwargs):
            self.messages.append({'role': role, 'message': text, 'asset_ids': kwargs.get('asset_ids', []), 'metadata': kwargs.get('metadata', {})})
            return len(self.messages)

        self.repo.add_conversation.side_effect = add_message
        self.tools = []

        def tools_factory(*args, **kwargs):
            tool = SelectionTools()
            self.tools.append(tool)
            return tool

        for patcher in (patch.object(api, 'WorkflowRepository', self.repo),
                        patch.object(api, '_require_canvas'), patch.object(api, 'session_tasks', return_value=[]),
                        patch.object(api, 'WorkflowTools', side_effect=tools_factory)):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def chat(self, client, message, session_id=None, **kwargs):
        with patch.object(api, '_get_llm_client', return_value=(client, 'test-model', 10000)):
            return await api._process_chat(api.ChatRequest(message=message, model_id=1, canvas_id=66, session_id=session_id, **kwargs), {'id': 4, 'user_id': 4})

    async def test_five_step_plan_survives_question_reload_and_resume(self):
        plan = fantasy_plan()
        first = await self.chat(client_for(plan, ready('天使站在云端。'), question('恶魔必须保留哪些外观特征？')), '三张角色图合照，再生成8秒视频')
        draft = self.session['parameters']['generation_draft']
        self.assertEqual(first.intent, 'generation_plan')
        self.assertIsNone(first.generation_request)
        self.assertFalse(first.workflow_ready)
        self.assertEqual(draft['request']['steps'], plan['steps'])
        self.assertEqual(len(draft['enhanced_steps']), 1)
        self.assertEqual(draft['step_id'], 's2')
        self.assertEqual(self.tools[0].calls, [])
        restored = api._load_chat_state(80, 4, 66)
        self.assertEqual(restored['generation_draft'], draft)
        client = client_for({'intent': 'resume_generation'}, ready('恶魔长着红色弯角。'), ready('精灵穿绿袍。'),
                            ready('天使和恶魔打斗，精灵在中间劝架。'), ready('参考合照，天使和恶魔打斗，精灵劝架，连续8秒。'))
        second = await self.chat(client, '恶魔长红色弯角，继续', 80)
        steps = second.generation_request['steps']
        self.assertEqual(len(steps), 5)
        self.assertEqual(steps[0]['prompt'], '天使站在云端。')
        self.assertEqual(steps[3]['depends_on'], ['s1', 's2', 's3'])
        self.assertEqual(steps[4]['depends_on'], ['s4'])
        self.assertEqual(steps[4]['duration'], 8)
        self.assertNotIn('generation_draft', self.session['parameters'])
        self.assertIn('generation_request', self.session['parameters'])
        self.assertFalse(second.workflow_ready)
        self.assertEqual(len(self.tools[1].calls), 1)
        self.assertEqual(client.chat.completions.create.await_count, 5)

    async def test_single_task_invalid_output_is_saved_and_retryable(self):
        client = client_for({'intent': 'txt2video', 'prompt': '精灵行走'}, ready('优化哪个模型的提示词？'), ready('请提供提示词'))
        first = await self.chat(client, '生成精灵视频')
        self.assertEqual(self.session['parameters']['generation_draft']['status'], 'retry')
        self.assertIsNone(first.generation_request)
        self.assertEqual(self.tools[0].calls, [])
        second = await self.chat(client_for({'intent': 'resume_generation'}, ready('精灵在森林中行走。')), '重试', 80)
        self.assertEqual(second.generation_request['media_type'], 'video')
        self.assertEqual(second.generation_request['prompt'], '精灵在森林中行走。')

    async def test_cancel_or_new_task_clears_old_draft(self):
        await self.chat(client_for(fantasy_plan(), question('天使有什么必须保留的外观特征？')), '生成三张角色图再合照和视频')
        await self.chat(client_for({'intent': 'chat'}, '已取消任务。'), '取消刚才任务', 80)
        self.assertEqual(self.session['parameters'], {})
        self.assertEqual(self.tools[1].calls, [])

    async def test_paused_draft_cannot_be_confirmed_as_ready_plan(self):
        await self.chat(client_for(fantasy_plan(), question('请补充天使必须保留的外观。')), '生成角色合照和视频')
        with self.assertRaises(api.HTTPException) as caught:
            await self.chat(client_for(), '确认生成', 80, generation_options={'media_type': 'plan', 'plan_id': 'old-plan'})
        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn('generation_draft', self.session['parameters'])
        self.assertEqual(self.tools[-1].calls, [])

    async def test_new_generation_replaces_old_draft(self):
        await self.chat(client_for(fantasy_plan(), question('请补充天使外观。')), '生成角色合照和视频')
        result = await self.chat(client_for({'intent': 'txt2img', 'prompt': '改成生成一只猫'}, ready('一只橘猫躺在窗边。')), '取消原计划，画一只猫', 80)
        self.assertEqual(result.generation_request['media_type'], 'image')
        self.assertNotIn('generation_draft', self.session['parameters'])

    async def test_new_reference_only_applies_to_paused_step(self):
        await self.chat(client_for(fantasy_plan(), ready('天使站在云端。'), question('请上传恶魔的参考图。')), '生成角色合照和视频')
        asset = {'id': 99, 'asset_type': 'picture', 'location': 'test-reference.png'}
        with patch.object(api, 'load_chat_assets', return_value=[asset]), patch.object(api, 'build_asset_content', side_effect=lambda text, *args: text):
            result = await self.chat(client_for({'intent': 'resume_generation'}, ready('恶魔参考用户图片。'), ready('精灵穿绿袍。'),
                                                ready('三人打斗合照。'), ready('参考合照连续运动8秒。')), '参考这张图', 80, asset_ids=[99])
        steps = result.generation_request['steps']
        self.assertEqual(steps[1]['input_asset_ids'], [99])
        self.assertTrue(all(not step['input_asset_ids'] for step in steps if step['id'] != 's2'))

    def test_edited_prompt_is_checked_before_confirmation(self):
        pending = {'media_type': 'video', 'prompt': '精灵在森林中行走。'}
        with self.assertRaises(api.HTTPException):
            api._apply_generation_edits(pending, {'prompt': '优化哪个模型的提示词？'})

    async def test_plain_prompt_optimization_does_not_create_generation(self):
        result = await self.chat(client_for({'intent': 'chat'}, '这是优化后的森林画面提示词。'), '只优化提示词，不生成')
        self.assertFalse(result.workflow_ready)
        self.assertEqual(self.tools[0].calls, [])

    async def test_node_optimization_will_not_fill_a_question_into_canvas(self):
        client = client_for({'status': 'ready', 'reply': '优化哪个模型？', 'prompt': '优化哪个模型的提示词？'},
                            {'status': 'question', 'reply': '请提供原始提示词。'})
        result = await self.chat(client, '优化节点提示词', prompt_optimization=True, skill_id='seedance-prompt')
        self.assertIsNone(result.optimized_prompt)
        self.assertEqual(result.reply, '请提供原始提示词。')
        self.assertEqual(self.tools[0].calls, [])

    async def test_node_optimization_requires_explicit_skill_even_with_history(self):
        self.messages.append({'role': 'user', 'message': '优化提示词', 'metadata': {
            'prompt_optimization': True, 'skill_id': 'seedance-prompt'}})
        for skill_id in (None, '', ' '):
            client = client_for()
            with self.assertRaises(api.HTTPException) as caught:
                await self.chat(client, '继续优化', 80, prompt_optimization=True, skill_id=skill_id)
            self.assertEqual(caught.exception.status_code, 400)
            client.chat.completions.create.assert_not_awaited()
        self.repo.create_session.assert_not_called()

    async def test_reverse_skill_receives_real_image_from_both_entries(self):
        with TemporaryDirectory() as directory:
            image_path = Path(directory) / 'reference.png'
            Image.new('RGB', (24, 16), 'red').save(image_path)
            asset = {'id': 19, 'asset_type': 'picture', 'rfid': 4, 'location': str(image_path)}
            document = {'nodes': [
                {'id': 'source', 'type': 'remote-imageNode', 'data': {'outputs': {
                    'image': {'dataType': 'IMAGE', 'value': {'assetIds': [19]}}}}},
                {'id': 'target', 'type': 'remote-imageGenerationNode', 'data': {}},
            ], 'edges': [{'source': 'source', 'target': 'target', 'sourceHandle': 'image'}]}
            for node_entry in (True, False):
                with self.subTest(node_entry=node_entry):
                    client = client_for(ready('红色画面。')) if node_entry else client_for({'intent': 'chat'}, '红色画面。')
                    kwargs = {'prompt_optimization': True, 'optimization_node_id': 'target'} if node_entry else {
                        'asset_ids': [19], 'asset_mentions': {19: '@图片2'}}
                    with patch.object(api, '_require_canvas', return_value={'document': json.dumps(document)}), \
                            patch.object(api, 'refresh_tasks', return_value=[]), \
                            patch('agents.services.chat_assets.asset_repo.get_assets_by_ids', return_value=[asset]) as lookup:
                        result = await self.chat(client, '请反推参考图片提示词' if node_entry else '请反推 @图片2 提示词',
                                                 skill_id='image-prompt-reverse', **kwargs)
                    lookup.assert_called_with([19])
                    messages = client.chat.completions.create.await_args_list[-1].kwargs['messages']
                    user_parts = [part for message in messages if message['role'] == 'user' and isinstance(message['content'], list)
                                  for part in message['content']]
                    self.assertTrue(any(part.get('image_url', {}).get('url', '').startswith('data:image/jpeg;base64,') for part in user_parts))
                    self.assertTrue(any(('@图片1' if node_entry else '@图片2') in part.get('text', '') for part in user_parts))
                    system_rules = '\n'.join(message['content'] for message in messages if message['role'] == 'system')
                    self.assertIn('通用图片分析框架', system_rules)
                    self.assertIn('主体与媒介专项分析', system_rules)
                    self.assertIn('插画画风专项分析', system_rules)
                    self.assertFalse(result.workflow_ready)
                    self.assertEqual(self.tools[-1].calls, [])


class ReverseSkillTest(unittest.TestCase):
    def test_skill_loads_complete_references_without_scripts(self):
        manager = SkillManager()
        instruction = manager.get_instruction('image-prompt-reverse')
        for title in ('通用图片分析框架', '主体与媒介专项分析', '插画画风专项分析'):
            self.assertIn(title, instruction)
        self.assertFalse((manager.skills['image-prompt-reverse']['path'] / 'scripts').exists())
        self.assertEqual(manager.get_skill_info('seedance-prompt')['info']['name'], 'Seedance 2.0 / 2.5 视频 & 图片提示词生成器')

    def test_upstream_images_follow_ports_and_edges_without_unrelated_assets(self):
        def output(kind, ids):
            return {'dataType': kind, 'value': {'assetIds': ids}}
        document = {'nodes': [
            {'id': 'source', 'type': 'remote-imageNode', 'data': {'outputs': {
                'image': output('IMAGE', [19, 20]), 'other': output('IMAGE', [99]), 'video': output('VIDEO', [70])}}},
            {'id': 'unused', 'type': 'remote-imageNode', 'data': {'outputs': {'image': output('IMAGE', [88])}}},
            {'id': 'target', 'type': 'remote-videoGenerationNode', 'data': {}},
        ], 'edges': [
            {'source': 'source', 'target': 'target', 'sourceHandle': port} for port in ('image', 'video', 'image')
        ]}
        self.assertEqual(node_reference_images(document, 'target'), ([19, 20], {19: '@图片1', 20: '@图片2'}))
        document['nodes'][0]['data']['task'] = {'state': 'pending'}
        with self.assertRaises(api.HTTPException):
            node_reference_images(document, 'target')
        document['nodes'][0]['data'].pop('task')
        document['edges'] = []
        with self.assertRaises(api.HTTPException):
            node_reference_images(document, 'target')
        with self.assertRaises(api.HTTPException):
            node_reference_images(document, 'removed')


if __name__ == '__main__':
    unittest.main()
