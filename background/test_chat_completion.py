"""普通对话的模型参数兼容性回归测试，不访问外网。"""
import json
import unittest
from unittest.mock import AsyncMock

import httpx
from openai import AsyncOpenAI

from agents.graph.nodes.tool_node import direct_execute_node


class ChatCompletionTest(unittest.IsolatedAsyncioTestCase):
    async def test_chat_works_with_restricted_model_parameters(self):
        requests = []

        def handle_request(request):
            body = json.loads(request.content)
            requests.append(body)
            # 模拟日志中拒绝旧参数的供应商响应。
            if 'max_tokens' in body:
                return httpx.Response(400, json={'error': {
                    'message': 'Unsupported parameter: max_tokens',
                    'type': 'invalid_request_error', 'param': 'max_tokens',
                    'code': 'unsupported_parameter',
                }})
            if body.get('temperature', 1) != 1:
                return httpx.Response(400, json={'error': {
                    'message': 'Only the default (1) temperature value is supported.',
                    'type': 'invalid_request_error', 'param': 'temperature',
                    'code': 'unsupported_value',
                }})
            return httpx.Response(200, json={
                'id': 'chat-test', 'object': 'chat.completion', 'created': 0,
                'model': body['model'],
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': '你好！'}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
            })

        on_usage = AsyncMock()
        async with AsyncOpenAI(
            api_key='test-key', base_url='https://model.test/v1',
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle_request)),
        ) as client:
            result = await direct_execute_node(
                {'intent': 'chat', 'messages': [
                    {'role': 'system', 'content': '用中文回答。'},
                    {'role': 'agent', 'content': '欢迎。'},
                    {'role': 'user', 'content': '你好'},
                ]},
                llm_client=client, model_name='restricted-model', on_usage=on_usage,
            )

        self.assertEqual(result, {'tool_result': {'reply': '你好！'}, 'is_complete': True})
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['model'], 'restricted-model')
        self.assertEqual(requests[0]['max_completion_tokens'], 1024)
        self.assertNotIn('max_tokens', requests[0])
        self.assertNotIn('temperature', requests[0])
        self.assertEqual([message['role'] for message in requests[0]['messages']], ['system', 'assistant', 'user'])
        on_usage.assert_awaited_once()
        self.assertEqual(on_usage.await_args.args[0].usage.total_tokens, 15)


if __name__ == '__main__':
    unittest.main()
