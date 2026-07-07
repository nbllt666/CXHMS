"""
补丁：在 Gemma4ReasoningParser 中添加 is_reasoning_end_streaming 方法，
使其在检测到 <|tool_call> token 时也认为 reasoning 已结束。

根因：BaseThinkingReasoningParser.is_reasoning_end_streaming 只检查 <channel|> 结束 token，
当模型不输出 reasoning 直接输出 <|tool_call> 时，reasoning_ended 永远不被设置为 True，
导致 extract_tool_calls_streaming 不被调用，<|tool_call> 作为 content 返回。

修复：覆盖 is_reasoning_end_streaming，同时检查 <channel|> 和 <|tool_call> token。
"""
import shutil
import subprocess
import sys


PATCH_METHOD = '''
    def is_reasoning_end_streaming(
        self, input_ids: Sequence[int], delta_ids: Iterable[int]
    ) -> bool:
        """Check if reasoning has ended in streaming mode.

        Overrides base implementation to also detect <|tool_call> token:
        when the model generates a tool call without preceding reasoning,
        we must end the reasoning phase to trigger tool call extraction.
        """
        # Check for <|channel|> end token (parent behavior)
        if self.end_token_id is not None and self.end_token_id in delta_ids:
            return True
        # Check for <|tool_call> token — triggers tool call phase
        if self.tool_call_token_id is not None and self.tool_call_token_id in delta_ids:
            return True
        return False
'''


def create_patched_file():
    """创建补丁后的文件内容"""
    container_path = "/usr/local/lib/python3.12/dist-packages/vllm/reasoning/gemma4_reasoning_parser.py"

    # 读取原文件
    result = subprocess.run(
        ["docker", "exec", "vllm-gemma4", "cat", container_path],
        capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        print(f"[FAIL] 读取原文件失败: {result.stderr}")
        return False

    original = result.stdout

    # 检查是否已经打过补丁
    if "is_reasoning_end_streaming" in original:
        print("[SKIP] 补丁已存在")
        return True

    # 找到 is_reasoning_end 方法的结尾，在后面插入新方法
    # is_reasoning_end 方法结束后是 "# ---" 注释行或下一个方法
    marker = "        return False\n\n    # ------------------------------------------------------------------\n    # Non-streaming path"

    if marker not in original:
        # 尝试另一种格式
        marker = "        return False\n\n    #"

    if marker not in original:
        print("[FAIL] 找不到插入位置")
        return False

    # 在 is_reasoning_end 方法后插入 is_reasoning_end_streaming
    patched = original.replace(marker, "        return False\n" + PATCH_METHOD + "\n    # ------------------------------------------------------------------\n    # Non-streaming path", 1)

    # 写入临时文件
    with open("patched_gemma4_reasoning_parser.py", "w", encoding="utf-8") as f:
        f.write(patched)

    print(f"[OK] 补丁文件已创建: patched_gemma4_reasoning_parser.py ({len(patched)} bytes)")
    return True


def apply_patch():
    """应用补丁到容器"""
    # 复制补丁文件到容器
    result = subprocess.run(
        ["docker", "cp", "patched_gemma4_reasoning_parser.py",
         "vllm-gemma4:/usr/local/lib/python3.12/dist-packages/vllm/reasoning/gemma4_reasoning_parser.py"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[FAIL] 复制补丁文件失败: {result.stderr}")
        return False

    print("[OK] 补丁已应用到容器")
    return True


def verify_patch():
    """验证补丁"""
    result = subprocess.run(
        ["docker", "exec", "vllm-gemma4", "python3", "-c",
         "from vllm.reasoning.gemma4_reasoning_parser import Gemma4ReasoningParser; "
         "print('is_reasoning_end_streaming' in dir(Gemma4ReasoningParser))"],
        capture_output=True, text=True
    )
    print(f"[VERIFY] is_reasoning_end_streaming 存在: {result.stdout.strip()}")
    return "True" in result.stdout


if __name__ == "__main__":
    if create_patched_file():
        if apply_patch():
            if verify_patch():
                print()
                print("=" * 60)
                print("补丁应用成功！请重启 vLLM 容器：")
                print("  docker restart vllm-gemma4")
                print("=" * 60)
            else:
                print("[FAIL] 验证失败")
        else:
            print("[FAIL] 应用补丁失败")
    else:
        print("[FAIL] 创建补丁文件失败")
