"""VLLMClient 单元测试。

覆盖修复点：
    - B6: 锁竞态修复（移除 ``_http_lock`` 全局串行）
    - C1: 并发解除 + ``httpx.AsyncClient`` 统一 + ``LLMFactory`` 线程安全

设计原则：
    - 不发真实 HTTP 请求（VLLMClient 的 chat/stream_chat 需 vLLM 后端）
    - 直接验证类结构与行为：``_http_lock`` 不存在、``max_concurrent`` 默认 4、
      ``_semaphore`` 配对 acquire/release 不抛 RuntimeError、``LLMFactory._clients_lock``
      存在
    - 源码静态扫描：无 ``requests`` / ``asyncio.to_thread`` 引用
"""

import asyncio
import inspect
import threading

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# B6: _http_lock 移除
# --------------------------------------------------------------------------- #


def test_b6_vllm_client_has_no_http_lock():
    """B6: VLLMClient 实例不再有 ``_http_lock`` 属性。

    回归断言：修复前 ``_http_lock = asyncio.Lock()`` 叠加在信号量之上作为全局互斥锁，
    ``_release_http`` 中 ``if self._http_lock.locked(): self._http_lock.release()``
    存在竞态（locked() 检查与 release() 之间非原子），触发 RuntimeError。
    修复后移除 ``_http_lock``，仅用 ``_semaphore`` 控并发。
    """
    from backend.core.llm.client import VLLMClient

    client = VLLMClient(host="http://localhost:8002", model="test-model")
    assert not hasattr(client, "_http_lock"), "VLLMClient 仍残留 _http_lock 属性"


def test_b6_vllm_client_source_no_http_lock_references():
    """B6: VLLMClient 源码中无 ``_http_lock`` 代码引用（仅注释/docstring 说明移除原因）。

    用 inspect.getsource 提取源码，匹配真正的代码引用模式（赋值/属性访问/方法调用）：
    ``self._http_lock``、``_http_lock.acquire``、``_http_lock.release``、
    ``_http_lock.locked``、``_http_lock = ``。注释（# 开头）与 docstring 不计。
    """
    import re

    from backend.core.llm.client import VLLMClient

    source = inspect.getsource(VLLMClient)
    # 代码引用模式：属性访问、方法调用、赋值
    code_pattern = re.compile(
        r"self\._http_lock\b|_http_lock\.(acquire|release|locked)|_http_lock\s*=\s"
    )
    # 排除注释行
    code_lines = [
        line for line in source.splitlines()
        if code_pattern.search(line) and not line.strip().startswith("#")
    ]
    assert code_lines == [], f"VLLMClient 源码仍有 _http_lock 代码引用: {code_lines}"


# --------------------------------------------------------------------------- #
# C1: max_concurrent 默认 4
# --------------------------------------------------------------------------- #


def test_c1_max_concurrent_default_is_4():
    """C1: VLLMClient.max_concurrent 默认值为 4（解除全局串行瓶颈）。

    回归断言：修复前 ``max_concurrent: int = 1`` 默认值强制所有 vLLM HTTP 请求串行；
    修复后默认 4，允许最多 4 路并发。
    """
    from backend.core.llm.client import VLLMClient

    sig = inspect.signature(VLLMClient.__init__)
    max_concurrent_default = sig.parameters["max_concurrent"].default
    assert max_concurrent_default == 4, (
        f"max_concurrent 默认值应为 4，实际为 {max_concurrent_default}"
    )


def test_c1_semaphore_bound_to_max_concurrent():
    """C1: ``_semaphore`` 与 ``_bg_semaphore`` 各自上限 = max_concurrent。

    回归断言：``_semaphore`` 控用户请求并发上限，``_bg_semaphore`` 控后台任务并发上限，
    两者独立于 ``_http_lock``，完全由 max_concurrent 控制。
    """
    from backend.core.llm.client import VLLMClient

    client = VLLMClient(max_concurrent=4)
    assert client._semaphore._value == 4
    assert client._bg_semaphore._value == 4


# --------------------------------------------------------------------------- #
# C1: 信号量配对 acquire/release 不抛 RuntimeError
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_b6_concurrent_acquire_release_no_runtime_error():
    """B6: 多次配对 acquire/release 信号量不抛 RuntimeError。

    回归断言：修复前 ``_release_http`` 的 ``if self._http_lock.locked():
    self._http_lock.release()`` 在并发下可能释放未持有的锁，触发
    ``RuntimeError: Release unlocked lock``。修复后仅释放信号量，配对 acquire/release
    不抛异常。
    """
    from backend.core.llm.client import VLLMClient

    client = VLLMClient(max_concurrent=4)

    # 多次配对 acquire/release（用户请求路径）
    for _ in range(20):
        await client._acquire_http(is_background=False)
        client._release_http(is_background=False)

    # 多次配对 acquire/release（后台任务路径）
    for _ in range(20):
        await client._acquire_http(is_background=True)
        client._release_http(is_background=True)

    # 信号量恢复到初始值（无泄漏）
    assert client._semaphore._value == 4
    assert client._bg_semaphore._value == 4


@pytest.mark.asyncio
async def test_b6_concurrent_acquire_does_not_serial():
    """B6: 多个并发 acquire 可同时持有信号量（不串行）。

    回归断言：修复前 ``_http_lock`` 全局互斥使所有请求串行；修复后仅信号量控制
    并发上限，4 个并发 acquire 可同时持有（不互相阻塞）。
    """
    from backend.core.llm.client import VLLMClient

    client = VLLMClient(max_concurrent=4)

    # 4 个并发 acquire 应全部成功（信号量上限内）
    await asyncio.gather(*[client._acquire_http() for _ in range(4)])
    assert client._semaphore._value == 0  # 4 个槽位已占满

    # 第 5 个 acquire 应阻塞（信号量耗尽）——用 wait_for 验证超时
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(client._acquire_http(), timeout=0.1)

    # 释放一个后，第 5 个应能获取
    client._release_http()
    await client._acquire_http()

    # 清理
    for _ in range(4):
        client._release_http()
    assert client._semaphore._value == 4


# --------------------------------------------------------------------------- #
# C1: httpx.AsyncClient 统一（无 requests / asyncio.to_thread 引用）
# --------------------------------------------------------------------------- #


def test_c1_no_requests_import_in_client_module():
    """C1: client.py 模块不再 import ``requests``。

    回归断言：修复前 ``chat``/``is_available``/``get_embedding`` 用同步 ``requests``
    + ``asyncio.to_thread`` 双栈；修复后统一用 ``httpx.AsyncClient``。
    """
    from backend.core.llm import client as client_module

    source = inspect.getsource(client_module)
    # 不应出现 import requests（注释中提及 requests 是允许的，说明移除原因）
    code_lines = [
        line for line in source.splitlines()
        if "import requests" in line and not line.strip().startswith("#")
    ]
    assert code_lines == [], f"client.py 仍有 import requests: {code_lines}"


def test_c1_no_asyncio_to_thread_in_vllm_client():
    """C1: VLLMClient 源码无 ``asyncio.to_thread`` 调用。

    回归断言：修复前 ``requests`` + ``asyncio.to_thread`` 伪装异步；
    修复后 ``chat``/``is_available``/``get_embedding`` 全用 ``httpx.AsyncClient``。
    """
    from backend.core.llm.client import VLLMClient

    source = inspect.getsource(VLLMClient)
    code_lines = [
        line for line in source.splitlines()
        if "asyncio.to_thread" in line and not line.strip().startswith("#")
    ]
    assert code_lines == [], f"VLLMClient 源码仍有 asyncio.to_thread: {code_lines}"


# --------------------------------------------------------------------------- #
# C1: LLMFactory._clients 线程安全
# --------------------------------------------------------------------------- #


def test_c1_llm_factory_has_clients_lock():
    """C1: LLMFactory 类有 ``_clients_lock`` 类变量（threading.Lock）。

    回归断言：修复前 ``_clients`` 类变量字典在多线程下读写无保护；
    修复后加 ``_clients_lock = threading.Lock()``，create_client/clear_cache 用 with 锁。
    """
    from backend.core.llm.client import LLMFactory

    assert hasattr(LLMFactory, "_clients_lock")
    assert isinstance(LLMFactory._clients_lock, type(threading.Lock()))


def test_c1_llm_factory_create_client_thread_safe():
    """C1: LLMFactory.create_client 多线程下不重复实例化（_clients_lock 双重检查锁定）。

    回归断言：多线程并发 create_client 同一 provider+kwargs 应返回缓存的同一实例，
    不会因竞态重复实例化。
    """
    from backend.core.llm.client import LLMFactory

    LLMFactory.clear_cache()

    instances = []
    barrier = threading.Barrier(4)

    def _worker():
        barrier.wait()
        client = LLMFactory.create_client(
            provider="ollama",
            host="http://localhost:11434",
            model="test-concurrent",
        )
        instances.append(client)

    threads = [threading.Thread(target=_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 4 个线程获取的应是同一实例（缓存命中）
    assert len(instances) == 4
    first = instances[0]
    for inst in instances[1:]:
        assert inst is first, "LLMFactory 多线程下重复实例化（_clients_lock 未生效）"

    LLMFactory.clear_cache()


def test_c1_llm_factory_clear_cache_thread_safe():
    """C1: LLMFactory.clear_cache 在多线程下不抛异常（_clients_lock 保护）。

    回归断言：clear_cache 与 create_client 并发执行时，_clients_lock 保护字典读写。
    """
    from backend.core.llm.client import LLMFactory

    LLMFactory.clear_cache()
    errors = []

    def _creator():
        try:
            for _ in range(10):
                LLMFactory.create_client(
                    provider="ollama",
                    host="http://localhost:11434",
                    model="clear-cache-test",
                )
        except Exception as e:
            errors.append(e)

    def _clearer():
        try:
            for _ in range(10):
                LLMFactory.clear_cache()
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=_creator)
    t2 = threading.Thread(target=_clearer)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors == [], f"LLMFactory 并发 clear_cache/create_client 抛异常: {errors}"
    LLMFactory.clear_cache()
