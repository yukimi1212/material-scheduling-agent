# 案例 01：正常排期与用户确认

## 1. 案例目的

验证 Agent 能否根据素材审核结果和当前排期情况，为无风险素材安排发布时间，并在用户确认后保存排期草稿。

本案例重点验证：

- 模型能否根据当前业务情况选择合适的工具。
- 模型能否根据工具返回的可用时段作出排期决策。
- 用户确认前是否只提出建议，不保存草稿。
- 用户确认后是否成功保存草稿。
- 保存结果和草稿列表是否一致。

## 2. 输入信息

**用户请求：**

```text
请安排素材 M004 在 21:00 发布。
```

**素材信息：**

- 素材 ID：M004
- 审核状态：passed
- 风险等级：low
- 风险原因：无

## 3. Agent 执行过程

### Step 1：模型选择工具

模型首先选择调用 `query_slots` 工具，查询素材 M004 当前可用的发布时间。

**模型决策：**

```json
{
  "action": "call_tool",
  "tool": "query_slots",
  "arguments": {
    "material_id": "M004"
  },
  "reason": "查询当前可用发布时间"
}
```

### Step 2：工具返回查询结果

工具成功返回当前排期信息：

```json
{
  "success": true,
  "occupied": [
    "18:00",
    "19:00",
    "20:00"
  ],
  "available": [
    "21:00"
  ],
  "message": "时段查询成功。"
}
```

查询结果表明：

- 18:00、19:00、20:00 已被占用。
- 21:00 是当前唯一可用时段。
- 用户指定的 21:00 可以安排。

### Step 3：模型根据观察结果作出决策

模型收到工具返回的信息后，选择 `propose_requested`，保留用户指定的发布时间。

**模型决策：**

```json
{
  "action": "propose_requested",
  "arguments": {
    "publish_time": "21:00",
    "reason": "指定时间 21:00 在 available 列表中，且审核结果无明显风险。",
    "question": "是否确认 21:00 为发布时间？"
  }
}
```

Agent 向用户提出确认请求。

**用户确认前的返回结果：**

```json
{
  "material_id": "M004",
  "review_status": "passed",
  "risk_level": "low",
  "requested_time": "21:00",
  "suggested_time": "21:00",
  "schedule_status": "pending_confirmation",
  "pending_items": [
    "等待用户确认发布时间 21:00"
  ],
  "draft_status": "not_saved",
  "message": "素材 M004 审核通过，建议发布时间为 21:00。是否保存排期草稿？（确认/取消）"
}
```

此时草稿尚未保存，Agent 等待用户确认。

## 4. 用户确认与草稿保存

**用户输入：**

```text
确认
```

用户确认后，Agent 调用草稿保存工具。

**实际返回结果：**

```json
{
  "material_id": "M004",
  "review_status": "passed",
  "risk_level": "low",
  "requested_time": "21:00",
  "suggested_time": "21:00",
  "schedule_status": "draft_saved",
  "pending_items": [],
  "draft_status": "saved",
  "message": "草稿保存成功。",
  "draft": {
    "material_id": "M004",
    "publish_time": "21:00",
    "schedule_request": {
      "requested_time": "21:00",
      "suggested_time": "21:00",
      "time_flexible": true
    },
    "review_status": "passed",
    "schedule_status": "draft_saved",
    "draft_status": "saved",
    "created_at": "2026-11-11T14:41:53"
  }
}
```

保存结果表明：

- `schedule_status` 为 `draft_saved`。
- `draft_status` 为 `saved`。
- `pending_items` 为空。
- 草稿中保存的发布时间为 21:00。

## 5. 保存结果验证

用户再次输入：

```text
查看草稿
```

系统返回目前共有 3 条草稿：

| 素材 ID | 发布时间 | 状态 |
|---|---|---|
| M004 | 21:00 | saved |
| M01 | 19:00 | saved |
| M01 | 20:00 | saved |

可以确认 M004 在 21:00 的新草稿已经成功保存，原有两条 M01 草稿也得到保留。

## 6. 测试结果

**测试结论：PASS**

本案例验证了正常排期流程：

1. Agent 完成素材审核，确认 M004 为低风险素材。
2. 模型选择 `query_slots` 工具查询可用时段。
3. Agent 将工具观察结果传递给模型。
4. 模型根据可用时段选择 `propose_requested`，保留用户指定的 21:00。
5. 用户确认之前，系统不保存草稿。
6. 用户确认后，草稿成功保存，状态更新为 `draft_saved`。
7. 通过查看草稿列表，验证新草稿真实存在。

本案例使用本地 Ollama 模型 `qwen3:1.7b` 进行真实运行测试，并非 Mock 模型测试。

**注意：本项目仅保存排期草稿，不执行真实内容发布。**