"""对话链路回归验证：执行真实图和流式接口，隔离数据库及外部模型。"""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).parent))

from agents.graph.subgraphs.prompt_enhance import llm_enhance_node


def load_routes():
    modules = {name: types.ModuleType(name) for name in (
        "api", "api.auth", "repositories", "repositories.workflow_repo",
        "repositories.generation_repo", "repositories.canvas_repo", "config", "agents.services.workflow_tools",
        "agents.services.chat_assets",
    )}
    modules["api"].__path__ = []
    modules["repositories"].__path__ = []
    modules["api.auth"].get_current_user = lambda: {"id": 4}
    modules["repositories.workflow_repo"].WorkflowRepository = Mock()
    modules["repositories.canvas_repo"].get_canvas = Mock(return_value={"id": 1})
    modules["repositories.generation_repo"].get_language_model_info = Mock()
    modules["config"].get_provider_config_by_rfid = Mock()
    modules["agents.services.workflow_tools"].WorkflowTools = Mock()
    modules["agents.services.workflow_tools"].session_tasks = Mock(return_value=[])
    assets = modules["agents.services.chat_assets"]
    assets.load_chat_assets = Mock(return_value=[])
    assets.build_asset_content = lambda message, _: message
    assets.asset_previews = Mock(return_value=[])
    spec = importlib.util.spec_from_file_location("workflow_chat_under_test", Path(__file__).parent / "api" / "workflow.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


def completion(content):
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))])


class WorkflowChatTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = load_routes()
        self.client = Mock()
        self.client.chat.completions.create = AsyncMock()
        self.api._get_llm_client = Mock(return_value=(self.client, "selected-model"))
        self.api._load_chat_state = Mock(return_value=None)
        self.api.WorkflowRepository.create_session.return_value = 31
        self.api.WorkflowRepository.add_conversation.side_effect = range(101, 121)
        self.tools = Mock(pending_generation=None, asset_ids=[])
        self.tools.allowed_asset_ids = set()
        self.tools.discover_and_execute = AsyncMock()
        self.api.WorkflowTools.return_value = self.tools

    def model_responses(self, intent="chat", prompt="", reply="人生的意义可以由自己创造。"):
        responses = [completion(json.dumps({"intent": intent, "prompt": prompt}))]
        if intent == "chat":
            responses.append(completion(reply))
        self.client.chat.completions.create.side_effect = responses

    def request(self, **kwargs):
        return self.api.ChatRequest(message="人生的意义是什么", model_id=7, canvas_id=1, **kwargs)

    async def run_graph(self, message="人生的意义是什么", existing_state=None):
        delta = AsyncMock()
        result = await self.api._run_conversation_graph(
            self.request(), self.tools, existing_state, message, self.id(), on_delta=delta,
        )
        return result, delta

    async def stream_events(self, request=None):
        events = []
        async for block in self.api._stream_chat_events(request or self.request(), {"id": 4}):
            if block.startswith("event:"):
                event, data = block.strip().split("\n", 1)
                events.append((event.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
        return events

    async def test_chat_reply_survives_graph_and_reaches_stream_and_storage(self):
        self.model_responses()
        events = await self.stream_events()
        delta = [data["text"] for event, data in events if event == "delta"]
        done = next(data for event, data in events if event == "done")
        self.assertEqual(delta, ["人生的意义可以由自己创造。"])
        self.assertEqual(done["reply"], delta[0])
        self.assertEqual(done["intent"], "chat")
        self.assertFalse(done["workflow_ready"])
        self.assertNotIn("error", [event for event, _ in events])
        traces = [data for event, data in events if event == "trace"]
        self.assertEqual([trace["type"] for trace in traces], ["model_request", "model_request"])
        self.assertEqual([trace["model"] for trace in traces], ["selected-model", "selected-model"])
        self.api.WorkflowRepository.add_conversation.assert_any_call(
            31, "agent", delta[0], metadata={"events": traces, "context_usage": None},
        )
        self.tools.discover_and_execute.assert_not_awaited()

    async def test_graph_tool_trace_reaches_stream_and_history(self):
        self.model_responses("txt2img", "一只猫")
        self.tools.discover_and_execute.return_value = {"task_id": "task-1"}
        events = await self.stream_events()
        traces = [data for event, data in events if event == "trace"]
        self.assertEqual([trace["type"] for trace in traces], ["model_request", "tool_call", "tool_result"])
        self.assertEqual(traces[1]["input"], {"prompt": "一只猫"})
        self.assertEqual(traces[2]["output"], {"task_id": "task-1"})
        self.assertEqual(traces[1]["call_id"], traces[2]["call_id"])
        self.api.WorkflowRepository.add_conversation.assert_any_call(
            31, "agent", "生成任务已提交，请查看下方进度。", metadata={"events": traces, "context_usage": None},
        )

    async def test_tool_failure_trace_precedes_stream_error(self):
        self.model_responses("txt2img", "一只猫")
        self.tools.discover_and_execute.return_value = {"error": "生成服务失败"}
        events = await self.stream_events()
        traces = [data for event, data in events if event == "trace"]
        self.assertEqual(traces[-1]["type"], "tool_result")
        self.assertEqual(traces[-1]["output"], {"error": "生成服务失败"})
        self.assertEqual(events[-1], ("error", {"message": "生成服务失败"}))

    async def test_confirmed_generation_also_reports_tool_trace(self):
        self.api._load_chat_state.return_value = {"messages": [], "generation_request": {"media_type": "image", "prompt": "猫"}}
        self.tools.discover_and_execute.return_value = {"task_id": "task-1"}
        events = await self.stream_events(self.request(session_id=31, generation_options={"media_type": "image", "model": 5}))
        traces = [data for event, data in events if event == "trace"]
        self.assertEqual([trace["type"] for trace in traces], ["tool_call", "tool_result"])
        self.assertEqual(traces[0]["name"], "txt2img")
        self.assertEqual(traces[0]["input"], {"prompt": "猫", "input_asset_ids": []})
        self.assertEqual(traces[1]["output"], {"task_id": "task-1"})

    async def test_model_failure_is_error_event_without_success_or_storage(self):
        self.client.chat.completions.create.side_effect = [
            completion('{"intent":"chat","prompt":""}'), RuntimeError("模型服务过载"),
        ]
        events = await self.stream_events()
        self.assertEqual(events[-1][0], "error")
        self.assertNotIn("delta", [event for event, _ in events])
        self.assertNotIn("done", [event for event, _ in events])
        self.assertIn("模型服务过载", events[-1][1]["message"])
        self.api.WorkflowRepository.add_conversation.assert_not_called()
        self.tools.discover_and_execute.assert_not_awaited()

    async def test_empty_model_reply_does_not_send_null(self):
        self.model_responses(reply=None)
        events = await self.stream_events()
        self.assertEqual(events[-1][0], "error")
        self.assertNotIn("delta", [event for event, _ in events])
        self.assertNotIn("done", [event for event, _ in events])

    async def test_tool_error_is_not_reported_as_processing(self):
        self.model_responses("txt2img", "一只猫")
        self.tools.discover_and_execute.return_value = {"error": "生成服务失败"}
        with self.assertRaises(HTTPException) as caught:
            await self.run_graph("画一张猫")
        self.assertEqual(caught.exception.detail, "生成服务失败")

    async def test_unexpected_empty_tool_result_is_an_error(self):
        self.model_responses("txt2img", "一只猫")
        self.tools.discover_and_execute.return_value = {}
        with self.assertRaises(HTTPException):
            await self.run_graph("画一张猫")

    async def test_pending_selection_is_not_wrapped_twice(self):
        self.model_responses("txt2img", "一只猫")
        pending = {"media_type": "image", "prompt": "一只猫", "models": [{"id": 5}]}
        self.tools.discover_and_execute.return_value = {"selection_required": pending}
        response = await self.api._process_chat(self.request(), {"id": 4})
        self.assertEqual(response.generation_request, pending)
        self.assertEqual(response.intent, "batch_image")
        self.api.WorkflowRepository.update_session.assert_any_call(31, parameters={"generation_request": pending})

    async def test_confirm_generation_with_or_without_reference_assets(self):
        for media_type, asset_ids in (("image", []), ("video", []), ("image", [41]), ("video", [41])):
            with self.subTest(media_type=media_type, asset_ids=asset_ids):
                tool_name = ("img2img" if media_type == "image" else "img2video") if asset_ids else ("txt2img" if media_type == "image" else "txt2video")
                pending = {"media_type": media_type, "prompt": "已确认的描述", "models": [{"id": 5}]}
                if asset_ids:
                    pending.update(input_asset_ids=asset_ids, tool_name=tool_name)
                self.api._load_chat_state.return_value = {"messages": [], "generation_request": pending}
                self.tools.discover_and_execute.return_value = {"task_id": "task-1"}
                response = await self.api._process_chat(self.request(session_id=31, generation_options={"media_type": media_type, "model": 5}), {"id": 4})
                self.assertTrue(response.workflow_ready)
                self.assertIsNone(response.generation_request)
                self.tools.discover_and_execute.assert_awaited_with(tool_name, {"prompt": "已确认的描述", "input_asset_ids": asset_ids})
                self.api.WorkflowRepository.update_session.assert_any_call(31, parameters={})
        self.api._get_llm_client.assert_not_called()

    async def test_changed_generation_type_is_rejected_before_execution(self):
        self.api._load_chat_state.return_value = {"messages": [], "generation_request": {"media_type": "image", "prompt": "猫"}}
        with self.assertRaises(HTTPException) as caught:
            await self.api._process_chat(self.request(session_id=31, generation_options={"media_type": "video"}), {"id": 4})
        self.assertEqual(caught.exception.status_code, 400)
        self.tools.discover_and_execute.assert_not_awaited()

    async def test_multi_step_request_keeps_dependencies_and_asks_for_confirmation(self):
        steps = [{'id': 'portrait', 'media_type': 'image', 'prompt': '人物', 'depends_on': []},
                 {'id': 'video', 'media_type': 'video', 'prompt': '人物挥手', 'depends_on': ['portrait'], 'duration': 8}]
        self.client.chat.completions.create.return_value = completion(json.dumps({'intent': 'generation_plan', 'steps': steps}))
        pending = {'media_type': 'plan', 'plan_id': 'plan-1', 'steps': steps}
        self.tools.discover_and_execute.return_value = {'selection_required': pending}
        result = await self.api._process_chat(self.request(), {'id': 4})
        self.assertEqual(result.intent, 'generation_plan')
        self.assertEqual(result.generation_request, pending)
        self.tools.discover_and_execute.assert_awaited_once_with('generation_plan', {'steps': steps})
        self.assertEqual(self.client.chat.completions.create.await_count, 1)

    async def test_confirmed_plan_uses_persisted_steps_without_another_model_call(self):
        pending = {'media_type': 'plan', 'plan_id': 'plan-1', 'steps': [{'id': 's1'}]}
        self.api._load_chat_state.return_value = {'messages': [], 'generation_request': pending}
        self.tools.confirm_plan = AsyncMock(return_value={'plan_id': 'plan-1', 'tasks': [{'status': 'queued'}]})
        response = await self.api._process_chat(self.request(session_id=31, generation_options={'media_type': 'plan', 'plan_id': 'plan-1'}), {'id': 4})
        self.assertTrue(response.workflow_ready)
        self.tools.confirm_plan.assert_awaited_once_with(pending)
        self.api._get_llm_client.assert_not_called()

    async def test_confirmation_failure_has_no_success_event(self):
        self.api._load_chat_state.return_value = {"messages": [], "generation_request": {"media_type": "image", "prompt": "猫"}}
        self.tools.discover_and_execute.return_value = {"error": "模型不可用"}
        events = await self.stream_events(self.request(session_id=31, generation_options={"media_type": "image", "model": 5}))
        self.assertEqual(events[-1], ("error", {"message": "模型不可用"}))
        self.assertNotIn("done", [event for event, _ in events])

    async def test_contextual_generation_uses_resolved_prompt(self):
        self.model_responses("txt2img", "夕阳下的一只橘猫")
        self.tools.discover_and_execute.return_value = {"task_id": "task-2"}
        result, _ = await self.run_graph("按刚才的描述来一张", {"messages": [{"role": "user", "content": "夕阳下的一只橘猫"}, {"role": "assistant", "content": "要生成图片吗？"}]})
        self.assertTrue(result["workflow_ready"])
        self.tools.discover_and_execute.assert_awaited_once_with("txt2img", {"prompt": "夕阳下的一只橘猫"})
        classification = self.client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(classification[-1]["content"], "按刚才的描述来一张")
        self.assertEqual(classification[1]["content"], "夕阳下的一只橘猫")

    async def test_chat_route_does_not_generate_for_image_questions_or_negation(self):
        for message in ("这张图片有什么问题", "不要生成视频，只解释一下"):
            with self.subTest(message=message):
                self.model_responses()
                result, _ = await self.run_graph(message)
                self.assertEqual(result["state"]["intent"], "chat")
                self.assertEqual(result["tasks"], [])
        self.tools.discover_and_execute.assert_not_awaited()

    async def test_multimodal_input_remains_intact_for_chat(self):
        self.model_responses()
        content = [{"type": "text", "text": "这张图片有什么问题"}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,test"}}]
        await self.run_graph(content)
        calls = self.client.chat.completions.create.call_args_list
        self.assertEqual(calls[0].kwargs["messages"][-1]["content"], "这张图片有什么问题")
        self.assertEqual(calls[1].kwargs["messages"][-1]["content"], content)

    async def test_invalid_classification_fails_without_executing_tools(self):
        for content in ("不是 JSON", '{"intent":"delete_all"}', '{"intent":"txt2img","prompt":""}'):
            self.client.chat.completions.create.side_effect = [completion(content)]
            with self.assertRaises(ValueError):
                await self.run_graph()
        self.tools.discover_and_execute.assert_not_awaited()

    async def test_prompt_enhancement_receives_selected_model(self):
        self.client.chat.completions.create.side_effect = [completion("优化后的描述")]
        result = await llm_enhance_node({"instruction": "优化视频提示词", "user_prompt": "猫在跑"}, self.client, "selected-model")
        self.assertEqual(result["enhanced_prompt"], "优化后的描述")
        self.assertEqual(self.client.chat.completions.create.call_args.kwargs["model"], "selected-model")

    async def test_video_graph_optimizes_with_selected_model_and_preserves_result(self):
        self.client.chat.completions.create.side_effect = [completion('{"intent":"txt2video","prompt":"猫在跑"}'), completion("优化后的视频描述")]
        self.tools.discover_and_execute.return_value = {"task_id": "video-task"}
        result, _ = await self.run_graph("生成猫在跑的视频")
        self.assertEqual(result["state"]["intent"], "txt2video")
        self.tools.discover_and_execute.assert_awaited_once_with("txt2video", {"prompt": "优化后的视频描述"})
        for call in self.client.chat.completions.create.call_args_list:
            self.assertEqual(call.kwargs["model"], "selected-model")

    async def test_missing_model_config_is_an_explicit_error(self):
        api = load_routes()
        api.get_language_model_info.return_value = None
        with self.assertRaises(HTTPException) as caught:
            api._get_llm_client(7)
        self.assertEqual(caught.exception.status_code, 404)
        api.get_language_model_info.return_value = {"rfid": 9, "name": "selected-model"}
        api.get_provider_config_by_rfid.return_value = None
        with self.assertRaises(HTTPException) as caught:
            api._get_llm_client(7)
        self.assertEqual(caught.exception.status_code, 500)


if __name__ == "__main__":
    unittest.main()
