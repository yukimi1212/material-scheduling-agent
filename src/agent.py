import re
import sys
import json
from pathlib import Path

try:
    from .llm import chat
    from .tools import (
        read_material,
        check_rules,
        query_slots,
        save_schedule_draft
    )
    from .storage import get_draft

except ImportError:
    from llm import chat
    from tools import (
        read_material,
        check_rules,
        query_slots,
        save_schedule_draft
    )
    from storage import get_draft


class Agent:
    def __init__(self, max_steps=6):
        self.max_steps = max_steps
        self.pending = None
        self.last_trace = []

    def _parse_decision(self, response):
        response = re.sub(
            r"<think>.*?</think>",
            "",
            response,
            flags=re.DOTALL
        )
        response = response.replace("```json", "").replace("```", "")

        match = re.search(r"\{.*\}", response, re.DOTALL)

        if not match:
            return None

        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None

    def _extract_request(self, user_input):
        material_match = re.search(
            r"\b(M\d+)\b",
            user_input,
            re.IGNORECASE
        )

        time_match = re.search(
            r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)",
            user_input
        )

        material_id = (
            material_match.group(1).upper()
            if material_match else None
        )

        requested_time = None

        if time_match:
            requested_time = (
                f"{int(time_match.group(1)):02d}:"
                f"{time_match.group(2)}"
            )

        hard_time = bool(re.search(
            r"必须|固定|严格|不能调整|不得更改|不可更改|"
            r"只能在|务必在",
            user_input
        ))

        return material_id, requested_time, hard_time

    def _result(
        self,
        material_id,
        review_status="not_checked",
        risk_level="unknown",
        risk_reasons=None,
        requested_time=None,
        suggested_time=None,
        schedule_status="not_scheduled",
        pending_items=None,
        draft_status="not_saved",
        message=""
    ):
        return {
            "material_id": material_id,
            "review_status": review_status,
            "risk_level": risk_level,
            "risk_reasons": risk_reasons or [],
            "requested_time": requested_time,
            "suggested_time": suggested_time,
            "schedule_status": schedule_status,
            "pending_items": pending_items or [],
            "draft_status": draft_status,
            "message": message
        }

    def _format_result(self, result):
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _handle_pending(self, user_input):
        text = user_input.strip().lower()

        if text in ["取消", "cancel", "no", "n", "不同意"]:
            result = self.pending["result"]
            result["schedule_status"] = "cancelled"
            result["draft_status"] = "not_saved"
            result["pending_items"] = []
            result["message"] = "用户取消操作，未保存草稿。"
            self.pending = None
            return self._format_result(result)

        if self.pending["stage"] == "choose_time":
            available = self.pending["available"]

            if user_input.strip() not in available:
                return (
                    "请选择一个可用时间："
                    + ", ".join(available)
                    + "。也可以输入取消。"
                )

            self.pending["suggested_time"] = user_input.strip()
            self.pending["stage"] = "confirm"

            result = self.pending["result"]
            result["suggested_time"] = user_input.strip()
            result["schedule_status"] = "pending_confirmation"
            result["pending_items"] = [
                f"等待确认是否接受替代时段 "
                f"{user_input.strip()}"
            ]
            result["message"] = (
                f"你选择了 {user_input.strip()}，"
                "请确认是否保存排期草稿。"
            )

            return self._format_result(result)


        if self.pending["stage"] == "confirm":
            if text not in [
                "确认", "确定", "是", "好的",
                "yes", "y", "confirm"
            ]:
                return "请回复「确认」或「取消」。"

            data = self.pending
            result = data["result"]
            publish_time = data["suggested_time"]

            # 捕获保存过程中可能发生的异常
            try:
                save_result = save_schedule_draft(
                    data["material_id"],
                    publish_time,
                    schedule_request={
                        "requested_time": data["requested_time"],
                        "suggested_time": publish_time,
                        "time_flexible": not data["hard_time"]
                    }
                )

            except Exception as e:
                save_result = {
                    "success": False,
                    "message": f"草稿保存失败：{e}"
                }

            # 无论保存成功还是失败，都结束本次确认状态
            self.pending = None

            if save_result.get("success"):
                result["suggested_time"] = publish_time
                result["schedule_status"] = "draft_saved"
                result["draft_status"] = "saved"
                result["pending_items"] = []
                result["message"] = save_result["message"]
                result["draft"] = save_result.get("draft")

                if result["draft"]:
                    result["draft"]["schedule_status"] = "draft_saved"

                if save_result.get("duplicate"):
                    result["message"] = (
                        "相同排期草稿已经存在，未重复创建。"
                    )

            else:
                result["schedule_status"] = "not_scheduled"
                result["draft_status"] = "failed"
                result["pending_items"] = []
                result["message"] = save_result.get(
                    "message",
                    "草稿保存失败，原因未知。"
                )

            return self._format_result(result)

        return "当前确认状态异常，请重新提交需求。"


    def _react_decide(
        self,
        user_input,
        material_id,
        requested_time,
        hard_time,
        review_result
    ):
        """
        Model-driven tool loop:
        model selects query_slots -> tool executes -> observation is
        returned to the model -> model decides the next action.
        max_steps limits model decision/tool-call rounds.
        """
        trace = []
        slots_result = None
        observation_received = False

        prompt = f"""
你是素材审核与发布排期 Agent。你必须通过工具结果作出排期决策。

用户需求：{user_input}
素材 ID：{material_id}
用户指定时间：{requested_time}
是否为硬性时间：{hard_time}
审核结果：{json.dumps(review_result, ensure_ascii=False)}

你可以选择：
1. 调用工具 query_slots，查询实时可用时段。
2. 在收到 query_slots 的工具结果后，决定 propose_requested、
   propose_alternative、block 或 ask_user。

第一次必须先调用 query_slots，不能在没有查询时段的情况下直接给出排期建议。
调用工具时只返回 JSON：
{{
  "action": "call_tool",
  "tool": "query_slots",
  "arguments": {{"material_id": "{material_id}"}},
  "reason": "查询当前可用发布时间"
}}

收到工具结果后，再根据实际结果作出下一步决策。
硬性时间不可用时必须 block；非硬性时间不可用时可以提出替代时间。
替代时间必须来自工具返回的 available。
模型不能保存草稿，也不能声称内容已经发布。
只返回合法 JSON，不要输出 Markdown。
"""

        for step in range(1, self.max_steps + 1):
            try:
                raw_response = chat(prompt)
            except Exception as exc:
                trace.append({
                    "step": step,
                    "type": "model_error",
                    "summary": str(exc)
                })
                self.last_trace = trace
                return {
                    "status": "incomplete",
                    "message": f"模型调用失败，流程未完成：{exc}"
                }, slots_result, trace

            decision = self._parse_decision(raw_response)
            trace.append({
                "step": step,
                "type": "model_decision",
                "decision": decision
            })

            if not decision or not isinstance(decision, dict):
                self.last_trace = trace
                return {
                    "status": "incomplete",
                    "message": "模型返回无法解析，流程未完成。"
                }, slots_result, trace

            action = decision.get("action")
            arguments = decision.get("arguments", {})
            if not isinstance(arguments, dict):
                self.last_trace = trace
                return {
                    "status": "incomplete",
                    "message": "模型决策参数格式错误，流程未完成。"
                }, slots_result, trace

            if action == "call_tool":
                tool_name = decision.get("tool")

                # Only expose the explicitly allowed read-only tool here.
                if tool_name != "query_slots":
                    trace.append({
                        "step": step,
                        "type": "tool_rejected",
                        "tool": tool_name,
                        "reason": "工具不在允许列表中"
                    })
                    prompt = (
                        prompt
                        + "\n上一步工具选择无效。只允许调用 query_slots，"
                          "请重新选择合法动作。"
                    )
                    continue

                tool_args = decision.get("arguments", {})

                if not isinstance(tool_args, dict):
                    tool_args = {}

                if tool_args.get("material_id") != material_id:
                    trace.append({
                        "step": step,
                        "type": "tool_rejected",
                        "tool": "query_slots",
                        "reason": "工具参数中的素材 ID 与用户请求不一致"
                    })

                    prompt += (
                        "\n工具参数错误，material_id 必须与用户请求中的素材 ID 一致。"
                        "请重新选择合法动作。"
                    )
                    continue

                try:
                    slots_result = query_slots(tool_args["material_id"])
                except Exception as exc:
                    slots_result = {
                        "success": False,
                        "message": f"时段查询工具执行失败：{exc}"
                    }

                observation_received = True
                trace.append({
                    "step": step,
                    "type": "tool_observation",
                    "tool": "query_slots",
                    "arguments": {"material_id": material_id},
                    "result": slots_result
                })

                prompt = f"""
用户需求：{user_input}
素材 ID：{material_id}
指定时间：{requested_time}
是否为硬性时间：{hard_time}
审核结果：{json.dumps(review_result, ensure_ascii=False)}

你刚才调用了 query_slots，工具返回结果如下：
{json.dumps(slots_result, ensure_ascii=False)}

请观察工具结果并决定下一步：
- 如果工具失败，选择 block 或 ask_user，不能编造可用时间。
- 如果指定时间在 available 中，选择 propose_requested。
- 如果指定时间不在 available 且是硬性时间，选择 block。
- 如果指定时间不在 available 且允许调整，从 available 中选择一个替代时间，选择 propose_alternative。
- 如果没有可用时间，选择 block。
- 不得保存草稿；必须等待用户确认。

只允许以下四种 action，必须选择其中一种：
- propose_requested
- propose_alternative
- block
- ask_user

决策规则：
1. 优先检查用户指定的时间是否在 available 列表中。
2. 如果用户指定时间在 available 中，必须选择 propose_requested，
   publish_time 必须等于用户指定时间。
3. 如果用户指定时间不在 available 中，且属于硬性时间，选择 block。
4. 如果用户指定时间不在 available 中，且允许调整，
   才能选择 propose_alternative。
5. 替代时间必须严格来自 available 列表。
6. occupied 中的时间绝对不能作为推荐时间。
7. 不得使用示例中的时间，不得根据记忆猜测时间。
8. 工具结果是唯一的时段判断依据。

返回 JSON，字段结构如下：
{{
    "action": "四种合法 action 之一",
    "arguments": {{
        "publish_time": "实际选择的 HH:MM",
        "reason": "根据工具返回结果说明决策依据",
        "question": "需要用户回答的问题"
    }}
}}

只返回合法 JSON，不要输出 Markdown。
"""
                continue

            if action in [
                "propose_requested",
                "propose_alternative",
                "block",
                "ask_user"
            ]:
                if not observation_received:
                    prompt += (
                        "\n你尚未收到时段查询工具结果，不能直接结束。"
                        "请先调用 query_slots。"
                    )
                    continue

                trace.append({
                    "step": step,
                    "type": "final_decision",
                    "action": action,
                    "arguments": arguments
                })
                self.last_trace = trace
                return decision, slots_result, trace

            trace.append({
                "step": step,
                "type": "invalid_action",
                "action": action
            })
            prompt += (
                "\n动作无效。请调用 query_slots，或在收到工具结果后"
                "选择合法的最终决策动作。"
            )

        trace.append({
            "step": self.max_steps,
            "type": "step_limit",
            "summary": "达到最大模型决策步数"
        })
        self.last_trace = trace
        return {
            "status": "incomplete",
            "message": (
                f"达到最大执行步数 {self.max_steps}，"
                "Agent 未能完成排期决策。"
            )
        }, slots_result, trace


    def run(self, user_input):
        # 清空上一次执行的 Trace
        self.last_trace = []

        material_id, requested_time, hard_time = (
            self._extract_request(user_input)
        )

        if not material_id:
            return self._format_result(
                self._result(
                    None,
                    pending_items=["请补充素材 ID"],
                    message="缺少素材 ID，无法开始排期。"
                )
            )

        if not requested_time:
            return self._format_result(
                self._result(
                    material_id,
                    pending_items=["请补充发布时间"],
                    message="缺少明确的发布时间，请提供 HH:MM 格式时间。"
                )
            )

        observations = []

        # Step 1: read material.
        material_result = read_material(material_id)
        observations.append({
            "tool": "read_material",
            "result": material_result
        })

        if not material_result["success"]:
            return self._format_result(
                self._result(
                    material_id,
                    pending_items=["素材不存在或无法读取"],
                    message=material_result["message"]
                )
            )

        if material_result.get("missing"):
            return self._format_result(
                self._result(
                    material_id,
                    pending_items=material_result.get(
                        "missing_fields",
                        ["补充素材信息"]
                    ),
                    message="素材信息不完整，暂时不能排期。"
                )
            )

        # Step 2: check review rules.
        review_result = check_rules(material_id)
        observations.append({
            "tool": "check_rules",
            "result": review_result
        })

        if not review_result["success"] or not review_result["can_schedule"]:
            return self._format_result(
                self._result(
                    material_id,
                    review_status=review_result.get(
                        "review_status", "not_checked"
                    ),
                    risk_level=review_result.get(
                        "risk_level", "unknown"
                    ),
                    risk_reasons=review_result.get(
                        "risk_reasons", []
                    ),
                    requested_time=requested_time,
                    pending_items=["处理审核风险后重新提交"],
                    message=review_result["message"]
                )
            )

        # Step 2.5: check whether the same draft already exists.
        existing = get_draft(material_id, requested_time)

        if existing["success"]:
            result = self._result(
                material_id,
                review_status=review_result["review_status"],
                risk_level=review_result["risk_level"],
                risk_reasons=review_result["risk_reasons"],
                requested_time=requested_time,
                suggested_time=requested_time,
                schedule_status="already_exists",
                draft_status="saved",
                message=(
                    f"素材 {material_id} 在 {requested_time} "
                    "已经存在排期草稿，未重复创建。"
                )
            )

            result["draft"] = existing["draft"]

            return self._format_result(result)

        # Step 3: model-driven ReAct loop.
        result = self._result(
            material_id,
            review_status=review_result["review_status"],
            risk_level=review_result["risk_level"],
            risk_reasons=review_result["risk_reasons"],
            requested_time=requested_time
        )

        decision, slots_result, trace = self._react_decide(
            user_input,
            material_id,
            requested_time,
            hard_time,
            review_result
        )

        if decision.get("status") == "incomplete":
            result["schedule_status"] = "incomplete"
            result["pending_items"] = ["重新提交请求或检查模型/工具状态"]
            result["message"] = decision["message"]
            result["trace"] = trace
            return self._format_result(result)

        if not slots_result or not slots_result.get("success"):
            result["schedule_status"] = "blocked"
            result["pending_items"] = ["检查时段查询工具后重新提交"]
            result["message"] = (
                decision.get("arguments", {}).get("reason")
                or (slots_result or {}).get(
                    "message", "时段查询失败，无法继续排期。"
                )
            )
            result["trace"] = trace
            return self._format_result(result)

        action = decision.get("action")
        args = decision.get("arguments", {})

        # Validate consistency between model action and requested time.
        if action == "propose_requested":
            model_time = args.get("publish_time")

            # Check whether the model used the requested time.
            if model_time is not None and model_time != requested_time:

                if (
                        not hard_time
                        and model_time in slots_result.get("available", [])
                ):
                    # The model selected an available alternative time
                    # but used the wrong action label.
                    action = "propose_alternative"

                    # Synchronise the corrected action with the decision.
                    decision["action"] = action

                    # Update the final_decision entry in the trace.
                    for item in trace:
                        if item.get("type") == "final_decision":
                            item["action"] = action

                else:
                    result["schedule_status"] = "blocked"
                    result["message"] = (
                        "模型决策动作与推荐时间不一致，"
                        "为避免错误排期，已阻断。"
                    )
                    result["trace"] = trace
                    return self._format_result(result)

        # A requested time that is unavailable cannot be proposed.
        if (
                action == "propose_requested"
                and requested_time not in slots_result.get("available", [])
        ):
            result["schedule_status"] = "blocked"
            result["message"] = (
                "用户指定时间不可用，模型却选择了原时间排期，"
                "已阻断。"
            )
            result["trace"] = trace
            return self._format_result(result)

        if action == "block":
            result["schedule_status"] = "blocked"
            result["message"] = args.get(
                "reason", "当前条件不满足，排期已阻断。"
            )
            result["trace"] = trace
            return self._format_result(result)

        if action == "ask_user":
            result["schedule_status"] = "pending_confirmation"
            result["pending_items"] = [
                args.get("question", "需要用户补充信息")
            ]
            result["message"] = args.get(
                "question", "请补充必要信息。"
            )
            result["trace"] = trace
            return self._format_result(result)

        available = slots_result["available"]

        if action == "propose_requested":
            if requested_time not in available:
                result["schedule_status"] = "blocked"
                result["message"] = (
                    "模型建议使用指定时间，但该时间不在可用列表中；"
                    "为避免错误排期，已阻断。"
                )
                result["trace"] = trace
                return self._format_result(result)
            suggested_time = requested_time

        elif action == "propose_alternative":
            if hard_time:
                result["schedule_status"] = "blocked"
                result["message"] = (
                    "用户指定的是硬性发布时间，不能自动更换时段。"
                )
                result["trace"] = trace
                return self._format_result(result)

            suggested_time = args.get("publish_time")
            if (
                suggested_time not in available
                or suggested_time == requested_time
            ):
                result["schedule_status"] = "blocked"
                result["message"] = (
                    "模型推荐的替代时间无效或不在可用列表中，"
                    "未保存草稿。"
                )
                result["trace"] = trace
                return self._format_result(result)

        else:
            result["schedule_status"] = "incomplete"
            result["message"] = f"不支持的决策动作：{action}"
            result["trace"] = trace
            return self._format_result(result)

        result["suggested_time"] = suggested_time
        result["trace"] = trace
        result["schedule_status"] = "pending_confirmation"
        result["pending_items"] = [
            f"等待用户确认发布时间 {suggested_time}"
        ]

        if suggested_time != requested_time:
            result["message"] = (
                f"你要求的 {requested_time} 已被占用。"
                f"建议替代时段为 {suggested_time}。"
                "是否接受该时段并保存排期草稿？（确认/取消）"
            )
        else:
            result["message"] = (
                f"素材 {material_id} 审核通过，"
                f"建议发布时间为 {suggested_time}。"
                "是否保存排期草稿？（确认/取消）"
            )

        self.pending = {
            "stage": "confirm",
            "material_id": material_id,
            "requested_time": requested_time,
            "suggested_time": suggested_time,
            "hard_time": hard_time,
            "result": result
        }

        return self._format_result(result)

    def handle(self, user_input):
        if self.pending:
            return self._handle_pending(user_input)

        return self.run(user_input)
