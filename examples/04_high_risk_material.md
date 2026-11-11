# 案例 04：高风险素材阻断

## 1. 案例目的

验证当素材审核发现高风险时，Agent 能否阻止排期，避免存在内容风险的素材进入后续发布流程。

本案例重点验证：

- Agent 能否识别高风险素材。
- 能否明确返回审核风险及具体原因。
- 是否优先遵循审核规则，而不是直接满足用户的发布时间要求。
- 是否阻止高风险素材生成排期草稿。

## 2. 输入信息

**用户请求：**

```text
请安排素材 M002 在 19:00 发布。
```

**素材信息：**

- 素材 ID：M002
- 风险等级：high
- 风险原因：
  - 素材包含未经核实的信息
  - 存在内容合规风险

## 3. Agent 实际返回结果

```json
{
  "material_id": "M002",
  "review_status": "blocked",
  "risk_level": "high",
  "risk_reasons": [
    "素材包含未经核实的信息",
    "存在内容合规风险"
  ],
  "requested_time": "19:00",
  "suggested_time": null,
  "schedule_status": "not_scheduled",
  "pending_items": [
    "处理审核风险后重新提交"
  ],
  "draft_status": "not_saved",
  "message": "发现高风险，阻断排期。"
}
```

## 4. 结果分析

Agent 识别到 M002 存在高风险，因此直接阻断排期。

实际返回结果说明：

- `review_status` 为 `blocked`：素材审核未通过。
- `risk_level` 为 `high`：素材被判定为高风险。
- `risk_reasons`：返回两项具体风险原因。
- `requested_time` 为 `19:00`：保留用户原始请求。
- `suggested_time` 为 `null`：没有生成替代发布时间。
- `schedule_status` 为 `not_scheduled`：没有进入排期流程。
- `pending_items`：提示需要先处理审核风险，再重新提交。
- `draft_status` 为 `not_saved`：没有保存排期草稿。

Agent 返回明确提示：

```text
发现高风险，阻断排期。
```

## 5. Trace 记录

本次 CLI 返回结果没有包含 `trace` 字段。

从实际输出可以确认 Agent 返回了高风险审核结果并阻断排期，但无法仅凭这次输出还原具体的工具调用过程，因此不补造 Trace。

## 6. 测试结果

**测试结论：PASS**

本案例验证了高风险素材的阻断逻辑：

1. Agent 识别到素材 M002 存在高风险。
2. 返回明确的风险等级和风险原因。
3. 没有生成发布时间建议。
4. 没有进入用户确认流程。
5. 没有保存排期草稿。

即使用户指定了发布时间，Agent 仍然优先遵循素材审核规则，没有绕过风险检查。

**注意：本项目仅保存排期草稿，不执行真实内容发布。**