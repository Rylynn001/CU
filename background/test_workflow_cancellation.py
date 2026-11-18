"""验证停止读取或断开连接后，不留下运行中的对话任务。"""
import asyncio
import unittest
from unittest.mock import patch

from api import workflow as api


class WorkflowCancellationTest(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_cancels_running_chat(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def process_chat(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        request = api.ChatRequest(message='你好', model_id=1, canvas_id=66)
        with patch.object(api, '_process_chat', side_effect=process_chat):
            stream = api._stream_chat_events(request, {'id': 4})
            await anext(stream)
            pending = asyncio.create_task(anext(stream))
            await asyncio.wait_for(started.wait(), timeout=2)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
            self.assertTrue(cancelled.is_set())

    async def test_stop_before_chat_starts_does_not_run_chat(self):
        request = api.ChatRequest(message='你好', model_id=1, canvas_id=66)
        with patch.object(api, '_process_chat') as process_chat:
            stream = api._stream_chat_events(request, {'id': 4})
            await anext(stream)
            await stream.aclose()
            process_chat.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
