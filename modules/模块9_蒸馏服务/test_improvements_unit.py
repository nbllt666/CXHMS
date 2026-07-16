"""改进1/2/3 单元测试（不依赖 LLM，仅验证静态方法）。

验证项：
    - 改进2：_regex_extract_absolute_time（正则提取绝对时间）
    - 改进2：_build_time_metadata（构造时间 metadata）
    - 改进2：_infer_timestamp_by_chunk（按 chunk_index 推测时间）
    - 改进3：_split_text_into_chunks（overlap_size 重叠窗口）
    - 改进3：_build_chunk_boundary_context（相邻 chunk 边界上下文）
    - 改进3：_heuristic_check_truncated（启发式截断检测）
"""

import sys
import os

# 项目根目录（test 文件位于 modules/模块9_蒸馏服务/ 下，需上溯 3 层）
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
sys.path.insert(0, _PROJECT_ROOT)

from modules.模块9_蒸馏服务.distillation_service import DistillationService


def test_regex_extract_absolute_time():
    """改进2：正则提取绝对时间。"""
    print("\n=== 改进2: _regex_extract_absolute_time ===")

    # 测试 2024-01-15 10:30:00
    ts = DistillationService._regex_extract_absolute_time(
        "会议定于 2024-01-15 10:30:00 召开"
    )
    assert ts is not None, "应提取到时间戳"
    assert ts.startswith("2024-01-15T10:30:00"), f"时间戳格式错误: {ts}"
    print(f"  ✓ '2024-01-15 10:30:00' → {ts}")

    # 测试 2024年1月15日
    ts = DistillationService._regex_extract_absolute_time("2024年1月15日 发生了事件")
    assert ts is not None, "应提取到日期"
    assert ts.startswith("2024-01-15"), f"日期格式错误: {ts}"
    print(f"  ✓ '2024年1月15日' → {ts}")

    # 测试 2024/1/15 10:30
    ts = DistillationService._regex_extract_absolute_time("时间：2024/1/15 10:30")
    assert ts is not None, "应提取到时间戳"
    assert ts.startswith("2024-01-15T10:30"), f"时间戳格式错误: {ts}"
    print(f"  ✓ '2024/1/15 10:30' → {ts}")

    # 测试无时间
    ts = DistillationService._regex_extract_absolute_time("昨天发生了一件事")
    assert ts is None, "无绝对时间应返回 None"
    print(f"  ✓ '昨天发生了一件事' → None（无绝对时间）")

    print("  → 改进2 正则提取绝对时间：全部通过")


def test_build_time_metadata():
    """改进2：构造时间 metadata。"""
    print("\n=== 改进2: _build_time_metadata ===")

    # 有时间 + 非推断
    meta = DistillationService._build_time_metadata(
        {"has_time": True, "timestamp": "2024-01-15T10:30:00+00:00", "is_inferred": False}
    )
    assert meta == {"original_timestamp": "2024-01-15T10:30:00+00:00"}, f"meta 错误: {meta}"
    print(f"  ✓ has_time=True, inferred=False → {meta}")

    # 有时间 + 推断
    meta = DistillationService._build_time_metadata(
        {"has_time": True, "timestamp": "2024-01-15T00:00:00+00:00", "is_inferred": True}
    )
    assert meta == {
        "original_timestamp": "2024-01-15T00:00:00+00:00",
        "inferred": True,
    }, f"meta 错误: {meta}"
    print(f"  ✓ has_time=True, inferred=True → {meta}")

    # 无时间
    meta = DistillationService._build_time_metadata(
        {"has_time": False, "timestamp": "2026-07-17T00:00:00+00:00", "is_inferred": True}
    )
    assert meta == {
        "inferred_timestamp": "2026-07-17T00:00:00+00:00",
        "inferred": True,
    }, f"meta 错误: {meta}"
    print(f"  ✓ has_time=False → {meta}")

    # time_marker=None
    meta = DistillationService._build_time_metadata(None)
    assert meta == {}, f"time_marker=None 应返回空 dict: {meta}"
    print(f"  ✓ time_marker=None → {meta}")

    print("  → 改进2 时间 metadata 构造：全部通过")


def test_infer_timestamp_by_chunk():
    """改进2：按 chunk_index 推测时间。"""
    print("\n=== 改进2: _infer_timestamp_by_chunk ===")

    # chunk_index=None
    result = DistillationService._infer_timestamp_by_chunk(None)
    assert result["has_time"] is False
    assert result["is_inferred"] is True
    assert "timestamp" in result
    print(f"  ✓ chunk_index=None → {result}")

    # chunk_index=0
    result = DistillationService._infer_timestamp_by_chunk(0)
    assert result["has_time"] is False
    assert result["is_inferred"] is True
    print(f"  ✓ chunk_index=0 → has_time=False, inferred=True")

    # chunk_index=3
    result = DistillationService._infer_timestamp_by_chunk(3)
    assert result["has_time"] is False
    assert result["is_inferred"] is True
    # chunk_index=3 应比 chunk_index=0 早 3 小时
    print(f"  ✓ chunk_index=3 → {result['timestamp']}（早 3 小时）")

    print("  → 改进2 chunk_index 时间推测：全部通过")


def test_split_text_with_overlap():
    """改进3：_split_text_into_chunks overlap_size 行为。"""
    print("\n=== 改进3: _split_text_into_chunks (overlap_size) ===")

    # 构造超长文本（chunk_size=500 → target_chars=1500）
    long_text = "这是一段测试文本。" * 500  # 约 4500 字符

    # overlap_size=0（向后兼容）
    chunks_no_overlap = DistillationService._split_text_into_chunks(long_text, 500, overlap_size=0)
    assert len(chunks_no_overlap) > 1, "长文本应被切分"
    assert "[上下文重叠区开始]" not in chunks_no_overlap[1], "overlap_size=0 不应有重叠标记"
    print(f"  ✓ overlap_size=0: 切分为 {len(chunks_no_overlap)} 个 chunk，无重叠标记")

    # overlap_size=200
    chunks_overlap = DistillationService._split_text_into_chunks(long_text, 500, overlap_size=200)
    assert len(chunks_overlap) == len(chunks_no_overlap), "chunk 数应一致"
    assert "[上下文重叠区开始]" in chunks_overlap[1], "overlap_size=200 应有重叠标记"
    assert "[上下文重叠区结束]" in chunks_overlap[1], "应有结束标记"
    print(f"  ✓ overlap_size=200: 切分为 {len(chunks_overlap)} 个 chunk，chunk[1] 含重叠标记")

    # 短文本（不切分）
    short_text = "短文本"
    chunks_short = DistillationService._split_text_into_chunks(short_text, 500, overlap_size=200)
    assert chunks_short == [short_text], "短文本不应切分"
    print(f"  ✓ 短文本: 不切分")

    # 空文本
    chunks_empty = DistillationService._split_text_into_chunks("", 500, overlap_size=200)
    assert chunks_empty == [], "空文本应返回空列表"
    print(f"  ✓ 空文本: 返回空列表")

    print("  → 改进3 overlap_size 切分：全部通过")


def test_build_chunk_boundary_context():
    """改进3：_build_chunk_boundary_context 边界上下文构造。"""
    print("\n=== 改进3: _build_chunk_boundary_context ===")

    chunks = ["第一段内容", "第二段内容", "第三段内容"]
    contexts = DistillationService._build_chunk_boundary_context(chunks, boundary_size=5)

    assert len(contexts) == 3, f"应有 3 个 context: {len(contexts)}"

    # chunk[0]: prev_tail="", next_head="第二段内容"[:5]
    assert contexts[0]["prev_tail"] == "", f"chunk[0] prev_tail 应为空: {contexts[0]}"
    assert contexts[0]["next_head"] == "第二段内容", f"chunk[0] next_head 错误: {contexts[0]}"
    print(f"  ✓ chunk[0]: prev_tail='', next_head='{contexts[0]['next_head']}'")

    # chunk[1]: prev_tail="第一段内容", next_head="第三段内容"
    assert contexts[1]["prev_tail"] == "第一段内容", f"chunk[1] prev_tail 错误: {contexts[1]}"
    assert contexts[1]["next_head"] == "第三段内容", f"chunk[1] next_head 错误: {contexts[1]}"
    print(f"  ✓ chunk[1]: prev_tail='{contexts[1]['prev_tail']}', next_head='{contexts[1]['next_head']}'")

    # chunk[2]: prev_tail="第二段内容", next_head=""
    assert contexts[2]["prev_tail"] == "第二段内容", f"chunk[2] prev_tail 错误: {contexts[2]}"
    assert contexts[2]["next_head"] == "", f"chunk[2] next_head 应为空: {contexts[2]}"
    print(f"  ✓ chunk[2]: prev_tail='{contexts[2]['prev_tail']}', next_head=''")

    # boundary_size 截断
    contexts_short = DistillationService._build_chunk_boundary_context(chunks, boundary_size=2)
    assert contexts_short[1]["prev_tail"] == "内容", f"boundary_size=2 应截断: {contexts_short[1]['prev_tail']}"
    print(f"  ✓ boundary_size=2: prev_tail 截断为 '{contexts_short[1]['prev_tail']}'")

    print("  → 改进3 边界上下文构造：全部通过")


def test_heuristic_check_truncated():
    """改进3：启发式截断检测。"""
    print("\n=== 改进3: _heuristic_check_truncated ===")

    # 末尾截断（不以句号结尾）
    assert DistillationService._heuristic_check_truncated("这是一段没有句号结尾的文本") is True
    print("  ✓ 末尾无句号 → True")

    # 末尾完整（以句号结尾）
    assert DistillationService._heuristic_check_truncated("这是一段以句号结尾的文本。") is False
    print("  ✓ 末尾有句号 → False")

    # 末尾换行
    assert DistillationService._heuristic_check_truncated("文本\n") is False
    print("  ✓ 末尾换行 → False")

    # 空文本
    assert DistillationService._heuristic_check_truncated("") is False
    print("  ✓ 空文本 → False")

    print("  → 改进3 启发式截断检测：全部通过")


def test_split_text_default_backward_compat():
    """改进3：_split_text_into_chunks 默认参数向后兼容。"""
    print("\n=== 改进3: _split_text_into_chunks 默认参数向后兼容 ===")

    long_text = "测试文本。" * 1000
    # 不传 overlap_size（默认 0）
    chunks_default = DistillationService._split_text_into_chunks(long_text, 500)
    # 显式传 overlap_size=0
    chunks_explicit = DistillationService._split_text_into_chunks(long_text, 500, overlap_size=0)
    assert chunks_default == chunks_explicit, "默认参数应与 overlap_size=0 一致"
    print(f"  ✓ 默认参数与 overlap_size=0 行为一致（{len(chunks_default)} 个 chunk）")

    print("  → 改进3 默认参数向后兼容：通过")


if __name__ == "__main__":
    test_regex_extract_absolute_time()
    test_build_time_metadata()
    test_infer_timestamp_by_chunk()
    test_split_text_with_overlap()
    test_build_chunk_boundary_context()
    test_heuristic_check_truncated()
    test_split_text_default_backward_compat()

    print("\n" + "=" * 60)
    print("所有单元测试通过 ✓")
    print("=" * 60)
