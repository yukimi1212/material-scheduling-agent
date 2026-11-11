
"""
Main entry point for the Material Scheduling Agent.
"""

import sys
import json
import argparse
from pathlib import Path

# Ensure the project root is in Python path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.llm import set_mock_mode
from src.agent import Agent
from src.storage import list_drafts


def main():
    parser = argparse.ArgumentParser(
        description="Material Scheduling Agent"
    )

    parser.add_argument(
        "--mock",
        action="store_true",
        help="使用离线 Mock 模式，不连接 Ollama"
    )

    args = parser.parse_args()

    # 切换模型运行模式
    set_mock_mode(args.mock)

    if args.mock:
        print("[运行模式] 离线 Mock 模式（不连接 Ollama）")
    else:
        print("[运行模式] Ollama 真实模型模式")

    # Initialize Agent.
    agent = Agent()

    print("=" * 55)
    print("       Material Scheduling Agent")
    print("=" * 55)
    print("Welcome! I can help you schedule material publishing.")
    print("Type 'exit' or 'quit' to stop.")
    print("Type '查看草稿' to see saved drafts.\n")

    while True:
        try:
            user_input = input("You: ").strip()

            # Exit command.
            if user_input.lower() in ["exit", "quit"]:
                print("Agent: Goodbye!")
                break

            if not user_input:
                continue

            # Show saved drafts.
            if user_input == "查看草稿":
                show_drafts()
                continue

            # Send user request to Agent.
            print("\nAgent: Processing your request...\n")

            result = agent.handle(user_input)

            # Display result.
            if isinstance(result, str):
                try:
                    parsed_result = json.loads(result)

                    if isinstance(parsed_result, dict):
                        print("Agent:")
                        print(json.dumps(
                            parsed_result,
                            ensure_ascii=False,
                            indent=2
                        ))
                    else:
                        print("Agent:", result)

                except json.JSONDecodeError:
                    print("Agent:", result)

            elif isinstance(result, dict):
                print("Agent:")
                print(json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2
                ))

            else:
                print("Agent:", result)

            print()

        except KeyboardInterrupt:
            print("\nAgent: Goodbye!")
            break

        except Exception as e:
            print(f"\nError: {e}\n")


def show_drafts():
    result = list_drafts()

    if not result["success"]:
        print("读取草稿失败：" + result["message"])
        return

    drafts = result["drafts"]

    if not drafts:
        print("目前没有保存任何草稿。")
        return

    print(f"\n目前共有 {result['count']} 条草稿：\n")

    for i, draft in enumerate(drafts, 1):
        # Support both old and new draft formats.
        status = draft.get(
            "draft_status",
            draft.get("status", "unknown")
        )

        print(f"草稿 {i}")
        print(f"素材 ID：{draft.get('material_id', 'unknown')}")
        print(f"发布时间：{draft.get('publish_time', 'unknown')}")
        print(f"状态：{status}")
        print(f"创建时间：{draft.get('created_at', 'unknown')}")
        print("-" * 40)


if __name__ == "__main__":
    main()
