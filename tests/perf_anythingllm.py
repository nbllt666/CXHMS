"""AnythingLLM 兼容 API 性能测量脚本。

测量各端点延迟，识别瓶颈。
"""
import base64
import json
import time

import requests

BASE = "http://localhost:8001/api/v1"
HEADERS = {"Content-Type": "application/json"}


def perf_test():
    print("=" * 60)
    print("性能测量")
    print("=" * 60)

    # 1. 非流式 chat 延迟
    t0 = time.monotonic()
    r = requests.post(
        f"{BASE}/workspace/default/chat",
        json={"message": "回复一个字: 好", "mode": "chat"},
        headers=HEADERS,
        timeout=60,
    )
    t_chat = time.monotonic() - t0
    print(f"\n1. 非流式 chat: {t_chat:.3f}s (status={r.status_code})")

    # 2. 流式 chat 延迟（首 token + 总时间）
    t0 = time.monotonic()
    r = requests.post(
        f"{BASE}/workspace/default/stream-chat",
        json={"message": "回复一个字: 好", "mode": "chat"},
        headers=HEADERS,
        stream=True,
        timeout=60,
    )
    first_token_t = None
    total_t = None
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        if first_token_t is None:
            first_token_t = time.monotonic() - t0
        try:
            d = json.loads(line[6:])
            if d.get("close") is True:
                total_t = time.monotonic() - t0
                break
        except Exception:
            continue
    print(f"2. 流式 chat: 首token={first_token_t:.3f}s, 总时间={total_t:.3f}s")

    # 3. 附件解析延迟（TXT）
    doc = "测试文档内容"
    b64 = base64.b64encode(doc.encode()).decode()
    t0 = time.monotonic()
    r = requests.post(
        f"{BASE}/workspace/default/chat",
        json={
            "message": "回复一个字: 好",
            "mode": "chat",
            "attachments": [
                {
                    "name": "t.txt",
                    "mime": "application/anythingllm-document",
                    "contentString": f"data:text/plain;base64,{b64}",
                }
            ],
        },
        headers=HEADERS,
        timeout=60,
    )
    t_att = time.monotonic() - t0
    print(f"3. TXT 附件 chat: {t_att:.3f}s (比纯 chat 增加 {t_att - t_chat:.3f}s)")

    # 4. 附件解析延迟（PDF）
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.cell(0, 10, "Test keyword")
    pdf_bytes = bytes(pdf.output())
    b64 = base64.b64encode(pdf_bytes).decode()
    t0 = time.monotonic()
    r = requests.post(
        f"{BASE}/workspace/default/chat",
        json={
            "message": "回复一个字: 好",
            "mode": "chat",
            "attachments": [
                {
                    "name": "t.pdf",
                    "mime": "application/anythingllm-document",
                    "contentString": f"data:application/pdf;base64,{b64}",
                }
            ],
        },
        headers=HEADERS,
        timeout=60,
    )
    t_pdf = time.monotonic() - t0
    print(f"4. PDF 附件 chat: {t_pdf:.3f}s (比纯 chat 增加 {t_pdf - t_chat:.3f}s)")

    # 5. context_manager 读取延迟
    t0 = time.monotonic()
    r = requests.get(f"{BASE}/workspace/default/chats", headers=HEADERS, timeout=10)
    t_chats = time.monotonic() - t0
    history = r.json().get("history", [])
    print(f"5. GET chats 历史: {t_chats:.3f}s (共 {len(history)} 条)")

    # 6. 纯附件解析延迟（不走 LLM，直接调用 parser）
    t0 = time.monotonic()
    from backend.core.document.parser import parse_attachments

    parse_attachments(
        [
            {
                "name": "t.txt",
                "mime": "application/anythingllm-document",
                "contentString": f"data:text/plain;base64,{b64}",
            }
        ]
    )
    t_parse_txt = time.monotonic() - t0
    print(f"\n6. 纯 TXT 解析: {t_parse_txt * 1000:.1f}ms")

    b64_pdf = base64.b64encode(pdf_bytes).decode()
    t0 = time.monotonic()
    parse_attachments(
        [
            {
                "name": "t.pdf",
                "mime": "application/anythingllm-document",
                "contentString": f"data:application/pdf;base64,{b64_pdf}",
            }
        ]
    )
    t_parse_pdf = time.monotonic() - t0
    print(f"7. 纯 PDF 解析: {t_parse_pdf * 1000:.1f}ms")

    # 分析
    print("\n" + "=" * 60)
    print("分析")
    print("=" * 60)
    llm_time = t_chat - t_parse_txt  # 粗略估算 LLM 时间
    print(f"LLM 调用时间（估算）: ~{llm_time:.3f}s")
    print(f"TXT 附件解析时间: {t_parse_txt * 1000:.1f}ms")
    print(f"PDF 附件解析时间: {t_parse_pdf * 1000:.1f}ms")
    print(f"持久化+读取时间: {t_chats:.3f}s")
    overhead = t_att - t_chat
    print(f"附件处理额外开销: {overhead:.3f}s")
    if overhead < 0.1:
        print("结论: 附件处理开销可忽略（<100ms），瓶颈在 LLM 调用")
    elif overhead < 0.5:
        print("结论: 附件处理开销较小（<500ms），可接受")
    else:
        print("结论: 附件处理开销较大（>500ms），建议优化")


if __name__ == "__main__":
    perf_test()
