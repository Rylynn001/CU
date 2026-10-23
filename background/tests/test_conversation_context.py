"""对话上下文回归测试，不访问真实模型或数据库。"""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agents.conversation_agent import ConversationAgent


MENU = "请问你想做什么？\n1. 短剧制作（从剧本到视频）\n2. 批量生图\n3. 单个视频生成\n4. 图生视频"


def model_response(data):
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=json.dumps(data, ensure_ascii=False))
    )])


class ConversationContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = ConversationAgent(api_key="test-key")
        self.create = AsyncMock()
        self.agent.client.chat.completions.create = self.create

    async def asyncTearDown(self):
        await self.agent.client.close()

    def saved_state(self, intent=None, parameters=None, ready=False):
        return {
            "session_id": "test-session",
            "user_id": 1,
            "messages": [
                {"role": "user", "content": "你是什么模型？"},
                {"role": "agent", "content": MENU},
            ],
            "intent": intent,
            "parameters": parameters or {},
            "missing_params": [],
            "workflow_ready": ready,
            "current_step": "parameter_extraction" if intent else "intent_recognition",
        }

    async def test_number_selection_receives_previous_menu(self):
        """模拟模型必须看到上轮菜单才能理解数字回答。"""
        async def respond(**kwargs):
            messages = kwargs["messages"]
            if "意图识别助手" in messages[0]["content"]:
                has_menu = {"role": "assistant", "content": MENU} in messages
                return model_response({"intent": "image_to_video" if has_menu else "unknown"})
            return model_response({})

        self.create.side_effect = respond
        result = await self.agent.process("4", "test-session", 1, self.saved_state())
        self.assertEqual(result["state"]["intent"], "image_to_video")
        self.assertIn("图片文件路径或资产 ID", result["reply"])
        self.assertFalse(result["workflow_ready"])

    async def test_parameter_extraction_uses_supported_roles(self):
        state = self.saved_state(intent="image_to_video")
        state["messages"].append({"role": "agent", "content": "请提供图片文件路径或资产 ID"})
        self.create.return_value = model_response({"image_path_or_id": 42})
        result = await self.agent.process("资产 42", "test-session", 1, state)
        sent = self.create.call_args.kwargs["messages"]
        self.assertTrue(all(msg["role"] in ("system", "user", "assistant") for msg in sent))
        self.assertEqual(sent[-2], {"role": "assistant", "content": "请提供图片文件路径或资产 ID"})
        self.assertEqual(result["state"]["parameters"], {"image_path_or_id": 42})
        self.assertIn("视频时长", result["reply"])

    async def test_number_without_menu_still_needs_clarification(self):
        """没有菜单上下文时，不能把数字强行当成任务编号。"""
        self.create.return_value = model_response({"intent": "unknown"})
        result = await self.agent.process("4", "test-session", 1)
        self.assertIsNone(result["state"]["intent"])
        self.assertTrue(result["reply"])
        self.assertNotEqual(result["reply"], MENU)

    async def test_consecutive_turns_keep_parameters_and_accept_correction(self):
        self.create.side_effect = [
            model_response({"intent": "image_to_video"}),
            model_response({}),
            model_response({"image_path_or_id": 42}),
            model_response({"duration": 5}),
            model_response({"model": "ark"}),
            model_response({"model": "invalid"}),
            model_response({"model": "openai"}),
        ]
        state = None
        results = []
        for message in ("我要图生视频", "资产 42", "5 秒", "ark", "改用 invalid", "改成 openai"):
            result = await self.agent.process(message, "test-session", 1, state)
            state = result["state"]
            results.append(copy.deepcopy(result))

        self.assertEqual(results[1]["state"]["parameters"], {"image_path_or_id": 42})
        self.assertIn("视频时长", results[1]["reply"])
        self.assertIn("使用哪个模型", results[2]["reply"])
        self.assertTrue(results[3]["workflow_ready"])
        self.assertFalse(results[4]["workflow_ready"])
        self.assertIn("参数验证失败", results[4]["reply"])
        self.assertTrue(results[5]["workflow_ready"])
        self.assertEqual(results[5]["parameters"], {
            "image_path_or_id": 42, "duration": 5, "model": "openai"
        })
        self.assertFalse(any(msg["content"] == "" for msg in state["messages"]))

    async def test_route_restores_database_history(self):
        from api import workflow

        self.create.side_effect = [model_response({"intent": "image_to_video"}), model_response({})]
        history = [{"role": msg["role"], "message": msg["content"]}
                   for msg in self.saved_state()["messages"]]
        with patch.object(workflow, "get_conversation_agent", return_value=self.agent), \
                patch.object(workflow.WorkflowRepository, "get_session", return_value={
                    "user_id": 1, "intent": None, "parameters": {}, "status": "collecting"
                }), \
                patch.object(workflow.WorkflowRepository, "get_conversations", return_value=history), \
                patch.object(workflow.WorkflowRepository, "add_conversation") as add, \
                patch.object(workflow.WorkflowRepository, "update_session") as update:
            response = await workflow.chat(
                workflow.ChatRequest(message="4", session_id="test-session"), {"id": 1}
            )

        sent = self.create.call_args_list[0].kwargs["messages"]
        self.assertIn({"role": "assistant", "content": MENU}, sent)
        self.assertEqual(response.session_id, "test-session")
        self.assertEqual(response.intent, "image_to_video")
        self.assertEqual(response.parameters, {})
        self.assertIn("图片文件路径或资产 ID", response.reply)
        self.assertEqual(add.call_count, 2)
        self.assertEqual(update.call_args.kwargs["intent"], "image_to_video")

    async def test_route_invalid_correction_clears_ready_status(self):
        from api import workflow

        self.create.return_value = model_response({"model": "invalid"})
        with patch.object(workflow, "get_conversation_agent", return_value=self.agent), \
                patch.object(workflow.WorkflowRepository, "get_session", return_value={
                    "user_id": 1, "intent": "image_to_video", "status": "ready",
                    "parameters": {"image_path_or_id": 42, "duration": 5, "model": "ark"}
                }), \
                patch.object(workflow.WorkflowRepository, "get_conversations", return_value=[]), \
                patch.object(workflow.WorkflowRepository, "add_conversation"), \
                patch.object(workflow.WorkflowRepository, "update_session") as update:
            response = await workflow.chat(
                workflow.ChatRequest(message="改用 invalid", session_id="test-session"), {"id": 1}
            )

        self.assertFalse(response.workflow_ready)
        self.assertIn("参数验证失败", response.reply)
        self.assertEqual(response.parameters["image_path_or_id"], 42)
        self.assertEqual(update.call_args.kwargs["status"], "collecting")

    async def test_stream_sends_progress_reply_and_session_state(self):
        from api import workflow

        async def process_chat(request, user, on_progress=None):
            await on_progress("正在结合对话上下文识别你的请求")
            return workflow.ChatResponse(
                reply="已理解你的需求", session_id="test-session",
                intent="image_to_video", parameters={"duration": 5}, workflow_ready=False
            )

        with patch.object(workflow, "_process_chat", side_effect=process_chat):
            response = await workflow.chat_stream(
                workflow.ChatRequest(message="继续", session_id="test-session"), {"id": 1}
            )
            events = [chunk async for chunk in response.body_iterator]

        stream = "".join(events)
        self.assertIn('event: progress\ndata: {"message": "正在准备对话上下文"}', stream)
        self.assertIn('event: progress\ndata: {"message": "正在结合对话上下文识别你的请求"}', stream)
        self.assertIn('event: delta\ndata: {"text": "已理解你的需求"}', stream)
        self.assertIn('event: done\ndata: {"reply": "已理解你的需求"', stream)


if __name__ == "__main__":
    unittest.main()
