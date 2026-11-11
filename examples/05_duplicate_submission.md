# 案例 05：重复提交

## 1. 案例目的

验证用户重复提交相同素材、相同发布时间的排期请求时，Agent 能否识别已经存在的排期草稿，避免重复创建。

本案例重点验证：

- 能否识别相同素材和发布时间的已有草稿。
- 是否返回明确的重复提交状态。
- 是否避免重复保存。
- 是否保留已有草稿信息。

## 2. 输入信息

**用户请求：**

```text
请安排素材 M004 在 21:00 发布。
```

**已有草稿：**

- 素材 ID：M004
- 发布时间：21:00
- 草稿状态：saved
- 创建时间：2026-11-11T14:41:53

该草稿来自案例 01，已经成功保存。

## 3. Agent 实际返回结果

```json
{
  "material_id": "M004",
  "review_status": "passed",
  "risk_level": "low",
  "risk_reasons": [],
  "requested_time": "21:00",
  "suggested_time": "21:00",
  "schedule_status": "already_exists",
  "pending_items": [],
  "draft_status": "saved",
  "message": "素材 M004 在 21:00 已经存在排期草稿，未重复创建。",
  "draft": {
    "material_id": "M004",
    "publish_time": "21:00",
    "schedule_request": {
      "requested_time": "21:00",
      "suggested_time": "21:00",
      "time_flexible": true
    },
    "review_status": "passed",
    "schedule_status": "pending_confirmation",
    "draft_status": "saved",
    "created_at": "2026-11-11T14:41:53"
  }
}
```

## 4. 结果分析

Agent 识别到相同素材和发布时间的草稿已经存在，因此直接返回重复提交结果。

实际返回结果说明：

- `schedule_status` 为 `already_exists`：识别到已有排期草稿。
- `draft_status` 为 `saved`：已有草稿处于已保存状态。
- `pending_items` 为空：不需要进一步确认。
- `message` 明确提示未重复创建。
- `draft` 返回已有草稿的信息，创建时间与案例 01 一致。

### 状态一致性检查

实际返回的内层 `draft.schedule_status` 为 `pending_confirmation`，与外层 `already_exists` 不一致。

这属于已有草稿状态字段的一致性问题，需要进一步检查持久化数据和重复提交分支的返回逻辑。

## 5. Trace 记录

本次 CLI 返回结果没有包含 `trace` 字段，因此不记录未实际观察到的模型决策或工具调用过程。

## 6. 测试结果

**测试结论：核心重复检测逻辑 PASS，状态一致性待修正。**

本案例验证了：

1. Agent 能识别 M004 在 21:00 已经存在草稿。
2. 返回 `already_exists`，而不是重新发起排期确认。
3. 返回已有草稿信息。
4. 没有提示用户再次确认保存。
5. 没有创建新的排期草稿。

后续还需要通过查看草稿列表确认草稿数量没有增加，并修正内层 `schedule_status` 的不一致问题。

**注意：本项目仅保存排期草稿，不执行真实内容发布。**