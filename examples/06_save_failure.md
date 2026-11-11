# 案例06：保存失败（Save Failure）

## 1. 测试目的

验证草稿保存失败时，Agent 能否正确处理异常，清除 pending 状态，并明确反映保存失败，避免将失败操作标记为成功。

## 2. 测试方式

本案例使用 Mock 故障注入进行单元测试，通过模拟草稿保存失败，验证 Agent 的异常处理逻辑。

测试命令：

```bash
python -m unittest tests.test_agent -v
```

对应测试用例：

```text
test_save_failure_clears_pending
```

## 3. 实际测试结果

```text
test_save_failure_clears_pending (tests.test_agent.TestAgent.test_save_failure_clears_pending)
测试保存失败后清除 pending 状态。
测试保存失败后清除 pending ... ok

----------------------------------------------------------------------
Ran 10 tests in 0.012s

OK
```

## 4. 测试结论

- 保存失败处理测试通过。
- Agent 能够在保存失败后清除 pending 状态。
- 不会将未成功保存的草稿错误地标记为已保存。

**测试类型：** Mock 故障注入单元测试。

**说明：** 本案例验证的是保存失败时的异常处理流程，不代表真实文件系统故障或真实 Ollama CLI 运行测试。