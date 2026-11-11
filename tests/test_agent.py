
import json
import unittest
from unittest.mock import patch

import src.agent as agent_module


class TestAgent(unittest.TestCase):

    def setUp(self):
        self.agent = agent_module.Agent()

        # 模拟正常读取素材
        self.read_material_result = {
            "success": True,
            "material_id": "M01",
            "missing": False,
            "message": "素材读取成功。",
            "material": {
                "name": "Material M01",
                "status": "ready",
                "metadata": {
                    "title": "Test material",
                    "description": "Normal material"
                }
            }
        }

        # 模拟审核通过
        self.review_result = {
            "success": True,
            "review_status": "passed",
            "risk_level": "low",
            "risk_reasons": [],
            "can_schedule": True,
            "message": "审核通过，无明显风险。"
        }

        # 模拟没有相同草稿
        self.no_existing_draft = {
            "success": False,
            "message": "草稿不存在"
        }

        # 模拟可用时段
        self.slots_result = {
            "success": True,
            "occupied": ["18:00"],
            "available": ["19:00", "20:00", "21:00"],
            "message": "时段查询成功。"
        }

    def mock_basic_tools(self):
        """Mock 正常情况下的工具调用。"""
        return (
            patch.object(
                agent_module,
                "read_material",
                return_value=self.read_material_result
            ),
            patch.object(
                agent_module,
                "check_rules",
                return_value=self.review_result
            ),
            patch.object(
                agent_module,
                "get_draft",
                return_value=self.no_existing_draft
            ),
            patch.object(
                agent_module,
                "query_slots",
                return_value=self.slots_result
            )
        )

    def mock_react_responses(self, final_decision):
        """模拟 ReAct：先选择工具，再根据工具结果作出决策。"""

        call_tool = {
            "action": "call_tool",
            "tool": "query_slots",
            "arguments": {"material_id": "M01"},
            "reason": "查询当前可用发布时间"
        }

        return [
            json.dumps(call_tool),
            json.dumps(final_decision)
        ]

    def patch_react_chat(self, final_decision):
        """Mock 两轮模型响应。"""

        return patch.object(
            agent_module,
            "chat",
            side_effect=self.mock_react_responses(final_decision)
        )

    def test_normal_schedule(self):
        """测试正常排期，确认后成功保存。"""

        patches = self.mock_basic_tools()

        with patches[0], patches[1], patches[2], patches[3], \
            self.patch_react_chat({
                "action": "propose_requested",
                "arguments": {}
            }), \
             patch.object(
                 agent_module,
                 "save_schedule_draft",
                 return_value={
                     "success": True,
                     "message": "草稿保存成功。",
                     "draft": {
                         "material_id": "M01",
                         "publish_time": "19:00"
                     }
                 }
             ) as mock_save:

            response = self.agent.handle("安排素材 M01 在 19:00 发布")
            result = json.loads(response)

            self.assertEqual(
                result["schedule_status"],
                "pending_confirmation"
            )
            self.assertEqual(result["draft_status"], "not_saved")

            # 用户确认
            response = self.agent.handle("确认")
            result = json.loads(response)

            self.assertEqual(result["draft_status"], "saved")
            self.assertEqual(
                result["schedule_status"],
                "draft_saved"
            )
            mock_save.assert_called_once()

        print("测试正常排期 ... ok")

    def test_alternative_time(self):
        """测试时间冲突时推荐替代时间，并等待用户确认。"""

        patches = self.mock_basic_tools()

        with patches[0], patches[1], patches[2], patches[3], \
                self.patch_react_chat({
                    "action": "propose_alternative",
                    "arguments": {
                        "publish_time": "19:00",
                        "reason": "18:00 已被占用"
                    }
                }), \
             patch.object(
                 agent_module,
                 "save_schedule_draft",
                 return_value={
                     "success": True,
                     "message": "草稿保存成功。"
                 }
             ) as mock_save:

            response = self.agent.handle("安排素材 M01 在 18:00 发布")
            result = json.loads(response)

            self.assertEqual(result["requested_time"], "18:00")
            self.assertEqual(result["suggested_time"], "19:00")
            self.assertEqual(
                result["schedule_status"],
                "pending_confirmation"
            )

            # 尚未确认时不能保存
            mock_save.assert_not_called()

            # 用户确认后才保存
            self.agent.handle("确认")
            mock_save.assert_called_once()

        print("测试冲突时推荐替代时间 ... ok")

    def test_cancel_schedule(self):
        """测试用户取消后不保存草稿。"""

        patches = self.mock_basic_tools()

        with patches[0], patches[1], patches[2], patches[3], \
                self.patch_react_chat({
                    "action": "propose_requested",
                    "arguments": {}
                }), \
             patch.object(
                 agent_module,
                 "save_schedule_draft"
             ) as mock_save:

            self.agent.handle("安排素材 M01 在 19:00 发布")

            response = self.agent.handle("取消")
            result = json.loads(response)

            self.assertEqual(result["schedule_status"], "cancelled")
            self.assertEqual(result["draft_status"], "not_saved")
            self.assertIsNone(self.agent.pending)

            mock_save.assert_not_called()

        print("测试用户取消排期 ... ok")

    def test_high_risk_material(self):
        """测试高风险素材被阻断。"""

        high_risk_result = {
            "success": True,
            "review_status": "blocked",
            "risk_level": "high",
            "risk_reasons": ["存在内容合规风险"],
            "can_schedule": False,
            "message": "发现高风险，阻断排期。"
        }

        with patch.object(
            agent_module,
            "read_material",
            return_value=self.read_material_result
        ), patch.object(
            agent_module,
            "check_rules",
            return_value=high_risk_result
        ), patch.object(
            agent_module,
            "chat"
        ) as mock_chat:

            response = self.agent.handle(
                "安排素材 M01 在 19:00 发布"
            )
            result = json.loads(response)

            self.assertEqual(result["review_status"], "blocked")
            self.assertEqual(result["risk_level"], "high")
            self.assertEqual(result["schedule_status"], "not_scheduled")

            # 风险未通过，不应调用模型决策
            mock_chat.assert_not_called()

        print("测试高风险素材阻断 ... ok")

    def test_missing_material_metadata(self):
        """测试素材信息不完整时阻止排期。"""

        incomplete_result = {
            "success": True,
            "material_id": "M01",
            "missing": True,
            "missing_fields": ["metadata"],
            "message": "素材信息不完整。"
        }

        with patch.object(
            agent_module,
            "read_material",
            return_value=incomplete_result
        ), patch.object(
            agent_module,
            "check_rules"
        ) as mock_check:

            response = self.agent.handle(
                "安排素材 M01 在 19:00 发布"
            )
            result = json.loads(response)

            self.assertEqual(
                result["schedule_status"],
                "not_scheduled"
            )
            self.assertEqual(result["draft_status"], "not_saved")
            self.assertIn("metadata", result["pending_items"])

            # 素材信息不完整，不应继续审核
            mock_check.assert_not_called()

        print("测试素材信息缺失 ... ok")

    def test_invalid_model_suggestion(self):
        """测试模型推荐不在可用列表中的时间。"""

        patches = self.mock_basic_tools()

        with patches[0], patches[1], patches[2], patches[3], \
                self.patch_react_chat({
                    "action": "propose_alternative",
                    "arguments": {
                        "publish_time": "22:00",
                        "reason": "模型错误推荐"
                    }
                }):

            response = self.agent.handle(
                "安排素材 M01 在 18:00 发布"
            )
            result = json.loads(response)

            self.assertEqual(result["draft_status"], "not_saved")
            self.assertIsNone(self.agent.pending)
            self.assertIn("不在可用列表中", result["message"])

        print("测试模型推荐非法时间 ... ok")

    def test_save_failure_clears_pending(self):
        """测试保存失败后清除 pending 状态。"""

        patches = self.mock_basic_tools()

        with patches[0], patches[1], patches[2], patches[3], \
            self.patch_react_chat({
                "action": "propose_requested",
                "arguments": {}
            }), \
             patch.object(
                 agent_module,
                 "save_schedule_draft",
                 return_value={
                     "success": False,
                     "message": "模拟磁盘写入失败"
                 }
             ):

            self.agent.handle("安排素材 M01 在 19:00 发布")

            self.assertIsNotNone(self.agent.pending)

            response = self.agent.handle("确认")
            result = json.loads(response)

            self.assertEqual(result["draft_status"], "failed")
            self.assertEqual(
                result["schedule_status"],
                "not_scheduled"
            )
            self.assertIsNone(self.agent.pending)
            self.assertIn("模拟磁盘写入失败", result["message"])

        print("测试保存失败后清除 pending ... ok")

    def test_max_steps_limit(self):
        """测试达到最大执行步数后返回未完成状态。"""

        self.agent = agent_module.Agent(max_steps=1)

        patches = self.mock_basic_tools()

        call_tool = {
            "action": "call_tool",
            "tool": "query_slots",
            "arguments": {"material_id": "M01"}
        }

        with patches[0], patches[1], patches[2], patches[3], \
             patch.object(
                 agent_module,
                 "chat",
                 return_value=json.dumps(call_tool)
             ) as mock_chat:

            response = self.agent.handle(
                "安排素材 M01 在 19:00 发布"
            )

            result = json.loads(response)

            self.assertEqual(
                result["schedule_status"],
                "incomplete"
            )

            self.assertIn("最大执行步数", result["message"])

            mock_chat.assert_called_once()

            self.assertIsNone(self.agent.pending)

    def test_react_observation_passed_to_next_model_call(self):
        final_decision = {
            "action": "propose_alternative",
            "arguments": {
                "publish_time": "19:00",
                "reason": "18:00 已被占用，19:00 可用",
                "question": "是否接受 19:00？"
            }
        }

        responses = self.mock_react_responses(final_decision)

        captured_prompts = []

        def fake_chat(prompt):
            captured_prompts.append(prompt)
            return responses[len(captured_prompts) - 1]

        mock_slots = {
            "success": True,
            "occupied": ["18:00"],
            "available": ["19:00", "20:00", "21:00"]
        }

        with patch.object(
                agent_module, "chat", side_effect=fake_chat
        ), patch.object(
            agent_module, "query_slots", return_value=mock_slots
        ):
            agent = agent_module.Agent()
            result = json.loads(agent.run("请安排素材 M01 在 18:00 发布"))

        # 确保模型调用了两次
        self.assertEqual(len(captured_prompts), 2)

        # 第一轮要求模型调用 query_slots
        self.assertIn("query_slots", captured_prompts[0])

        # 第二轮必须包含工具返回的实际观察结果
        second_prompt = captured_prompts[1]

        self.assertIn("query_slots", second_prompt)
        self.assertIn("occupied", second_prompt)
        self.assertIn("available", second_prompt)

        # 确认工具结果确实传递给了第二轮模型
        self.assertIn("18:00", second_prompt)
        self.assertIn("19:00", second_prompt)

        # 最终决策应该是替代时间，而不是直接保存
        self.assertEqual(
            result["schedule_status"],
            "pending_confirmation"
        )
        self.assertEqual(result["suggested_time"], "19:00")
        self.assertEqual(result["draft_status"], "not_saved")

    def test_requested_time_conflict_with_wrong_action(self):
        """测试模型动作与推荐时间不一致时，Agent 能正确修正。"""

        final_decision = {
            "action": "propose_requested",
            "arguments": {
                "publish_time": "21:00",
                "reason": "21:00 可用"
            }
        }

        responses = self.mock_react_responses(final_decision)

        mock_slots = {
            "success": True,
            "occupied": ["18:00", "19:00", "20:00"],
            "available": ["21:00"],
            "message": "时段查询成功。"
        }

        with patch.object(
                agent_module,
                "chat",
                side_effect=responses
        ), patch.object(
            agent_module,
            "query_slots",
            return_value=mock_slots
        ):
            agent = agent_module.Agent()
            result = json.loads(
                agent.run("请安排素材 M01 在 18:00 发布")
            )

        # 模型虽然选择 propose_requested，
        # 但推荐时间与用户指定时间不同，应修正为替代时间。
        self.assertEqual(
            result["schedule_status"],
            "pending_confirmation"
        )
        self.assertEqual(result["suggested_time"], "21:00")
        self.assertEqual(result["draft_status"], "not_saved")
        self.assertIn("21:00", result["message"])


if __name__ == "__main__":
    unittest.main()
