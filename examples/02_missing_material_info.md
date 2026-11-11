# 案例 02：素材信息缺失

## 1. 案例目的

验证当素材缺少必要元数据时，Agent 能否识别信息不足并阻止排期，避免在素材信息不完整的情况下生成排期草稿。

本案例重点验证：

- Agent 能否识别素材元数据缺失。
- 能否正确标记审核状态和风险等级。
- 能否阻止不完整素材进入排期流程。
- 是否避免保存未经审核的排期草稿。

## 2. 输入信息

**用户请求：**

```text
请安排素材 M003 在 19:00 发布。
```

**素材信息：**

- 素材 ID：M003
- 元数据：缺失必要信息

## 3. Agent 实际返回结果

```json
{
  "material_id": "M003",
  "review_status": "not_checked",
  "risk_level": "unknown",
  "risk_reasons": [],
  "requested_time": null,
  "suggested_time": null,
  "schedule_status": "not_scheduled",
  "pending_items": [
    "metadata"
  ],
  "draft_status": "not_saved",
  "message": "素材信息不完整，暂时不能排期。"
}
```

## 4. 结果分析

Agent 识别到素材 M003 缺少必要元数据，因此没有继续执行排期。

实际返回结果说明：

- `review_status` 为 `not_checked`：素材尚未完成审核。
- `risk_level` 为 `unknown`：由于素材信息不完整，无法判断风险等级。
- `requested_time` 和 `suggested_time` 均为 `null`：没有生成发布时间建议。
- `schedule_status` 为 `not_scheduled`：素材未进入排期。
- `pending_items` 包含 `metadata`：明确指出仍需补充素材元数据。
- `draft_status` 为 `not_saved`：没有保存排期草稿。

Agent 返回明确提示：

```text
素材信息不完整，暂时不能排期。
```

## 5. Trace 记录

本次 CLI 返回结果没有包含 `trace` 字段，因此本案例不记录模型决策或工具调用过程，避免将未实际观察到的执行步骤作为真实记录。

## 6. 测试结果

**测试结论：PASS**

本案例验证了素材信息缺失场景下的阻断逻辑：

1. Agent 识别到 M003 的必要元数据缺失。
2. 未将未审核素材判定为低风险。
3. 没有生成发布时间建议。
4. 没有进入用户确认流程。
5. 没有保存排期草稿。

Agent 能够在输入信息不完整时停止排期，并明确告知用户需要补充元数据。

**注意：本项目仅保存排期草稿，不执行真实内容发布。**