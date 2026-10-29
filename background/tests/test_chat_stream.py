"""聊天流与工具调用的离线回归测试，不连接数据库、Redis 或模型服务。"""
import asyncio
import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import workflow
from agents.conversation_agent import ConversationAgent
from repositories import generation_repo
from services.workflow_tools import WorkflowTools


def text_chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=[]))])


def tool_chunk(name, arguments, call_id="call-1", index=0):
    fragment = SimpleNamespace(index=index, id=call_id, function=SimpleNamespace(name=name, arguments=arguments))
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[fragment]))])


class ModelStream:
    def __init__(self, chunks, error=None):
        self.chunks = chunks
        self.error = error
        self.close = AsyncMock()

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk
        if self.error:
            raise self.error


class ChatStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_events_keep_order_and_done_follows_all_text(self):
        async def process(request, user, progress, delta):
            await progress("正在处理")
            await delta("你")
            await asyncio.sleep(0)
            await delta("好")
            return workflow.ChatResponse(reply="你好", session_id=1, workflow_ready=False)

        with patch.object(workflow, "_process_chat", side_effect=process):
            response = await workflow.chat_stream(workflow.ChatRequest(message="你好", model_id=1), {"id": 1})
            events = [event async for event in response.body_iterator]
        self.assertEqual([item.splitlines()[0] for item in events], [
            "event: progress", "event: progress", "event: delta", "event: delta", "event: done",
        ])
        result = json.loads(events[-1].split("data: ", 1)[1])
        self.assertEqual(result["reply"], "你好")
        self.assertEqual(result["tasks"], [])
        self.assertEqual(response.media_type, "text/event-stream")
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")

    async def test_failure_produces_error_event(self):
        with patch.object(workflow, "_process_chat", side_effect=ValueError("模型不可用")):
            events = [event async for event in workflow._stream_chat_events(workflow.ChatRequest(message="你好", model_id=1), {"id": 1})]
        self.assertIn("event: error", events[-1])
        self.assertIn("模型不可用", events[-1])
        self.assertFalse(any("event: done" in event for event in events))

    async def test_closing_stream_cancels_running_chat(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def process(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with patch.object(workflow, "_process_chat", side_effect=process):
            stream = workflow._stream_chat_events(workflow.ChatRequest(message="你好", model_id=1), {"id": 1})
            await anext(stream)
            await asyncio.wait_for(started.wait(), timeout=1)
            await stream.aclose()
        self.assertTrue(cancelled.is_set())

    async def test_heartbeat_does_not_cancel_chat_or_leave_queue_reader(self):
        event_queue = asyncio.Queue()
        chat_task = asyncio.create_task(asyncio.Event().wait())
        real_wait = asyncio.wait
        queue_readers = []

        async def short_wait(tasks, **kwargs):
            self.assertEqual(kwargs["timeout"], 15)
            queue_readers.extend(task for task in tasks if task is not chat_task)
            return await real_wait(tasks, timeout=0.001, return_when=kwargs["return_when"])

        try:
            with patch.object(workflow.asyncio, "wait", side_effect=short_wait):
                event = await workflow._wait_for_chat_event(event_queue, chat_task)
            self.assertIsNone(event)
            self.assertFalse(chat_task.done())
            self.assertTrue(queue_readers[0].cancelled())
            await event_queue.put(("delta", {"text": "后续文字"}))
            self.assertEqual((await workflow._wait_for_chat_event(event_queue, chat_task))[1]["text"], "后续文字")
        finally:
            chat_task.cancel()
            await asyncio.gather(chat_task, return_exceptions=True)

    async def test_cancelling_wait_cleans_up_queue_reader(self):
        chat_task = asyncio.create_task(asyncio.Event().wait())
        waiting = asyncio.Event()
        queue_readers = []
        real_wait = asyncio.wait

        async def tracked_wait(tasks, **kwargs):
            queue_readers.extend(task for task in tasks if task is not chat_task)
            waiting.set()
            return await real_wait(tasks, **kwargs)

        try:
            with patch.object(workflow.asyncio, "wait", side_effect=tracked_wait):
                waiter = asyncio.create_task(workflow._wait_for_chat_event(asyncio.Queue(), chat_task))
                await waiting.wait()
                waiter.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await waiter
            self.assertTrue(queue_readers[0].cancelled())
            self.assertFalse(chat_task.done())
        finally:
            chat_task.cancel()
            await asyncio.gather(chat_task, return_exceptions=True)

    async def test_new_session_is_created_once_when_tool_needs_it(self):
        async def agent_process(**kwargs):
            ensure_session = tools.call_args.args[1]
            self.assertEqual(ensure_session(), 123)
            self.assertEqual(ensure_session(), 123)
            return {"reply": "任务已提交", "state": {"intent": "batch_image", "parameters": {}}, "tasks": [{"task_id": "t1"}]}

        agent = SimpleNamespace(process=AsyncMock(side_effect=agent_process))
        with patch.object(workflow, "WorkflowRepository") as repo, patch.object(workflow, "WorkflowTools") as tools, patch.object(workflow, "get_conversation_agent", return_value=agent), patch.object(workflow, "session_tasks", return_value=[]):
            repo.create_session.return_value = 123
            result = await workflow._process_chat(workflow.ChatRequest(message="画一只猫", model_id=1), {"id": 1})
            workflow.get_conversation_agent.assert_called_once_with(1)
            repo.create_session.assert_called_once_with(1)
            self.assertEqual(repo.add_conversation.call_count, 2)
            self.assertEqual(repo.update_session.call_args.kwargs["status"], "executing")
        self.assertEqual(result.session_id, 123)

    async def test_failed_new_chat_does_not_create_session(self):
        agent = SimpleNamespace(process=AsyncMock(side_effect=ValueError("模型失败")))
        with patch.object(workflow, "WorkflowRepository") as repo, patch.object(workflow, "WorkflowTools"), patch.object(workflow, "get_conversation_agent", return_value=agent):
            with self.assertRaisesRegex(ValueError, "模型失败"):
                await workflow._process_chat(workflow.ChatRequest(message="你好", model_id=1), {"id": 1})
            repo.create_session.assert_not_called()
            repo.add_conversation.assert_not_called()

    async def test_foreign_session_is_rejected_before_reading_messages(self):
        with patch.object(workflow, "WorkflowRepository") as repo:
            repo.get_session.return_value = {"user_id": 2}
            with self.assertRaises(workflow.HTTPException) as error:
                workflow._load_chat_state("other-session", 1)
            self.assertEqual(error.exception.status_code, 403)
            repo.get_conversations.assert_not_called()


class LanguageModelSelectionTests(unittest.TestCase):
    def test_language_model_lookup_uses_selected_id_and_language_type(self):
        with patch.object(generation_repo, "execute_query", return_value={"id": 27}) as execute_query:
            result = generation_repo.get_language_model_info(27)

        self.assertEqual(result, {"id": 27})
        execute_query.assert_called_once_with(
            "SELECT id, name, provider, rfid FROM api_models WHERE id = %s AND type = %s",
            (27, "language"),
            fetch_one=True,
        )

    def test_agent_uses_model_selected_by_request(self):
        model_info = {"id": 27, "name": "selected-model", "rfid": 3}
        provider_config = {"api_key": "key", "base_url": "url"}
        with patch.object(workflow, "get_language_model_info", return_value=model_info) as lookup, \
                patch.object(workflow, "get_provider_config_by_rfid", return_value=provider_config), \
                patch.object(workflow, "ConversationAgent") as agent_type:
            workflow.get_conversation_agent(27)

        lookup.assert_called_once_with(27)
        agent_type.assert_called_once_with(api_key="key", base_url="url", model="selected-model")

    def test_generation_options_require_explicit_values(self):
        tools = WorkflowTools({"id": 1}, lambda: 1, {"media_type": "video", "model": 4})

        self.assertIsNone(tools._selected_generation_options("video", ("model", "ratio", "resolution", "duration")))
        result = tools._request_generation_selection("video", {"prompt": "海边日落"})
        self.assertEqual(result["selection_required"]["prompt"], "海边日落")
        self.assertEqual(result["selection_required"]["media_type"], "video")


class ConversationAgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.agent = ConversationAgent.__new__(ConversationAgent)
        self.agent.model = "offline-test"
        self.create = AsyncMock()
        self.agent.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=self.create)))

    async def run_agent(self, **kwargs):
        return await self.agent.process(message="画一只猫", session_id=None, user_id=1, **kwargs)

    async def test_fragmented_tool_calls_and_results_round_trip(self):
        tool = {"type": "function", "function": {"name": "txt2img", "description": "生成图片", "parameters": {}}}
        streams = [
            ModelStream([tool_chunk("discover_", '{"query":', "discover"), tool_chunk("tools", '"生成图片"}', None)]),
            ModelStream([tool_chunk("txt2img", '{"model": 1, "prompt": "猫"}', "generate")]),
            ModelStream([text_chunk("任务"), text_chunk("已提交")]),
        ]
        requests = []

        async def create(**kwargs):
            requests.append(copy.deepcopy(kwargs))
            return streams[len(requests) - 1]

        self.create.side_effect = create
        discover = Mock(return_value=[tool])
        execute = AsyncMock(return_value={"task_id": "t1", "parameters": {"model": 1, "prompt": "猫"}})
        delta = AsyncMock()
        result = await self.run_agent(tool_discoverer=discover, tool_executor=execute, on_delta=delta)
        discover.assert_called_once_with("生成图片")
        execute.assert_awaited_once_with("txt2img", {"model": 1, "prompt": "猫"})
        self.assertEqual(len(requests[0]["tools"]), 1)
        self.assertEqual(len(requests[1]["tools"]), 2)
        self.assertEqual(requests[1]["messages"][-1]["tool_call_id"], "discover")
        self.assertEqual(json.loads(requests[2]["messages"][-1]["content"])["task_id"], "t1")
        self.assertEqual(result["reply"], "任务已提交")
        self.assertEqual(result["state"]["intent"], "batch_image")
        self.assertTrue(result["workflow_ready"])
        self.assertEqual([call.args[0] for call in delta.await_args_list], ["任务", "已提交"])
        for stream in streams:
            stream.close.assert_awaited_once()

    async def test_undiscovered_or_invalid_tool_is_reported_to_model(self):
        for name, arguments in [("txt2img", "{}"), ("discover_tools", "{")]:
            with self.subTest(name=name):
                self.create.side_effect = [ModelStream([tool_chunk(name, arguments)]), ModelStream([text_chunk("执行失败")])]
                execute = AsyncMock()
                result = await self.run_agent(tool_executor=execute)
                execute.assert_not_awaited()
                context = self.create.call_args.kwargs["messages"]
                self.assertIn("error", json.loads(context[-1]["content"]))
                self.assertFalse(result["workflow_ready"])

    async def test_partial_text_survives_model_failure_after_submission(self):
        self.create.side_effect = [
            ModelStream([tool_chunk("discover_tools", '{"query":"生成图片"}', "discover")]),
            ModelStream([tool_chunk("txt2img", "{}", "submit")]),
            ModelStream([text_chunk("已开始")], error=ValueError("流读取失败")),
        ]
        tool = {"type": "function", "function": {"name": "txt2img", "description": "生成图片"}}
        result = await self.run_agent(tool_discoverer=Mock(return_value=[tool]), tool_executor=AsyncMock(return_value={"task_id": "t1", "parameters": {}}))
        self.assertTrue(result["reply"].startswith("已开始"))
        self.assertIn("不影响已提交的任务", result["reply"])
        self.assertEqual(len(result["tasks"]), 1)

    async def test_stream_is_closed_when_reading_fails(self):
        stream = ModelStream([text_chunk("部分文字")], error=ValueError("读取失败"))
        self.create.return_value = stream
        parts = []
        with self.assertRaisesRegex(ValueError, "读取失败"):
            await self.agent._request_model([], [], None, parts, None)
        stream.close.assert_awaited_once()
        self.assertEqual(parts, ["部分文字"])

    async def test_keywords_force_discovery_only_in_first_round(self):
        self.assertEqual(self.agent._choose_tool("帮我写即梦视频提示词", 0, None)["function"]["name"], "discover_tools")
        self.assertIsNone(self.agent._choose_tool("帮我写即梦视频提示词", 1, None))
        self.assertIsNone(self.agent._choose_tool("你好", 0, None))

    async def test_discovery_keeps_keyword_scoring_and_case_matching(self):
        tools = WorkflowTools({"id": 1}, lambda: "s1")
        found = tools.discover("图片模型 生图模型 文生图 生成图片")
        self.assertEqual([tool["function"]["name"] for tool in found], ["list_image_models", "txt2img"])
        self.assertEqual(tools.discover("IMAGE MODEL")[0]["function"]["name"], "list_image_models")
        self.assertEqual(tools.discover("画一只猫"), [])

    async def test_history_is_preserved_and_agent_role_is_converted(self):
        state = {"messages": [{"role": "user", "content": "用哪个模型"}, {"role": "agent", "content": "请选择"}], "parameters": {}}
        self.create.return_value = ModelStream([text_chunk("你好")])
        await self.run_agent(existing_state=state)
        messages = self.create.call_args.kwargs["messages"]
        self.assertEqual([message["role"] for message in messages], ["system", "user", "assistant", "user"])


if __name__ == "__main__":
    unittest.main()
