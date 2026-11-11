
import json
import re
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:1.7b"

# 是否启用离线 Mock 模式
MOCK_MODE = False


def set_mock_mode(enabled=False):
    """切换真实模型或离线 Mock 模式。"""
    global MOCK_MODE
    MOCK_MODE = enabled


def mock_chat(prompt):
    """
    离线模拟模型决策。

    第一次调用：选择 query_slots。
    第二次调用：根据工具返回的 available 决定下一步。
    """

    # 第一次模型调用：选择查询时段工具
    if "你刚才调用了 query_slots" not in prompt:
        # 从 Prompt 中提取素材 ID
        material_match = re.search(
            r"素材 ID：\s*(M\d+)",
            prompt
        )

        material_id = (
            material_match.group(1)
            if material_match else None
        )

        return json.dumps({
            "action": "call_tool",
            "tool": "query_slots",
            "arguments": {
                "material_id": material_id
            },
            "reason": "先查询当前可用发布时间"
        }, ensure_ascii=False)

    # 第二次模型调用：读取工具观察结果
    requested_match = re.search(
        r"指定时间：(\d{2}:\d{2})",
        prompt
    )

    requested_time = (
        requested_match.group(1)
        if requested_match else None
    )

    hard_match = re.search(
        r"是否为硬性时间：\s*(True|False)",
        prompt
    )
    hard_time = (
        hard_match.group(1) == "True"
        if hard_match else False
    )

    # 提取工具返回的 available 列表
    available_match = re.search(
        r'"available"\s*:\s*(\[[^\]]*\])',
        prompt
    )

    available = []

    if available_match:
        available = json.loads(available_match.group(1))

    # 工具失败或没有可用时段
    if not available:
        return json.dumps({
            "action": "block",
            "arguments": {
                "reason": "没有可用时段，暂时无法排期。"
            }
        }, ensure_ascii=False)

    # 指定时间可用
    if requested_time in available:
        return json.dumps({
            "action": "propose_requested",
            "arguments": {
                "publish_time": requested_time,
                "reason": "工具返回结果显示指定时间可用。"
            }
        }, ensure_ascii=False)

    # 指定时间不可用，且属于硬性要求
    if hard_time:
        return json.dumps({
            "action": "block",
            "arguments": {
                "reason": "指定时间不可用，且用户要求不能调整。"
            }
        }, ensure_ascii=False)

    # 非硬性时间：选择工具返回的第一个可用时间
    return json.dumps({
        "action": "propose_alternative",
        "arguments": {
            "publish_time": available[0],
            "reason": "指定时间不可用，选择工具返回的第一个可用时段。"
        }
    }, ensure_ascii=False)


def chat(prompt):
    """调用真实 Ollama 模型，或使用离线 Mock。"""

    if MOCK_MODE:
        return mock_chat(prompt)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "think": False,
                "stream": False
            },
            timeout=120
        )

        response.raise_for_status()

        result = response.json()
        content = result.get("message", {}).get("content")

        if not content:
            raise ValueError("Ollama 返回了空响应。")

        return content

    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "无法连接 Ollama，请检查 Ollama 是否已经启动。"
        )

    except requests.exceptions.Timeout:
        raise RuntimeError(
            "Ollama 请求超时，请检查模型运行状态。"
        )

    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(
            f"Ollama HTTP 请求失败：{exc}"
        )

    except (ValueError, KeyError) as exc:
        raise RuntimeError(
            f"Ollama 返回的数据格式异常：{exc}"
        )


if __name__ == "__main__":
    result = chat("请用一句话介绍你自己。")
    print(result)
