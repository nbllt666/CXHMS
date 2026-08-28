"""backend.core.config.reinit 的单元测试。

覆盖 ReinitManager 在以下场景下的行为：
    1. decide_components：models 段变化 → {model_router, llm_client}
    2. decide_components：database 段变化 → 空集合（skipped）
    3. decide_components：纯阈值变化 → 空集合（skipped）
    4. decide_components：空 diff → 空集合
    5. reinit：单个组件失败时其他组件仍执行（隔离）
    6. get_status：无任务时返回 idle 状态

mock 策略：
    - ServiceState 用真实实例（无外部依赖，update_component 只做属性赋值）
    - ReinitManager.reinit_component 用 monkeypatch 替换为 mock，避免真实
      创建 MemoryManager/ACPManager 等需要 IO 的组件
    - decide_components 是纯逻辑，不需要 mock
"""

import asyncio
from typing import Set

import pytest

from backend.core.config.diff import ConfigDiff
from backend.core.config.reinit import ReinitManager, ReinitResult
from backend.dependencies import ServiceState


# --------------------------------------------------------------------------- #
# 辅助：构造 ReinitManager（不依赖真实 settings）
# --------------------------------------------------------------------------- #


def _make_manager() -> ReinitManager:
    """构造一个 ReinitManager 实例，注入空 ServiceState 和 None settings。

    decide_components 不使用 settings，因此传 None 安全。
    """
    state = ServiceState()
    return ReinitManager(service_state=state, settings=None)


# --------------------------------------------------------------------------- #
# 测试用例 1：models 段变化
# --------------------------------------------------------------------------- #


def test_decide_models_change():
    """diff 含 models 段 → 返回 {model_router, llm_client}"""
    mgr = _make_manager()
    diff = ConfigDiff(
        changed_sections={"models"},
        field_changes=["models.main.model"],
    )

    components = mgr.decide_components(diff)

    assert components == {"model_router", "llm_client"}


# --------------------------------------------------------------------------- #
# 测试用例 2：database 段变化 → 跳过
# --------------------------------------------------------------------------- #


def test_decide_database_change_skipped():
    """diff 含 database 段 → 返回空集合，skip_reason='database'"""
    mgr = _make_manager()
    diff = ConfigDiff(
        changed_sections={"database"},
        field_changes=["database.path"],
    )

    components = mgr.decide_components(diff)

    assert components == set()
    assert mgr._skip_reason == "database"


# --------------------------------------------------------------------------- #
# 测试用例 3：纯阈值变化 → 跳过
# --------------------------------------------------------------------------- #


def test_decide_pure_threshold_skipped():
    """diff 只含 memory.dedup_threshold → 返回空集合，skip_reason='pure_param'"""
    mgr = _make_manager()
    diff = ConfigDiff(
        changed_sections={"memory"},
        field_changes=["memory.dedup_threshold"],
    )

    components = mgr.decide_components(diff)

    assert components == set()
    assert mgr._skip_reason == "pure_param"


# --------------------------------------------------------------------------- #
# 测试用例 4：空 diff
# --------------------------------------------------------------------------- #


def test_decide_empty_diff():
    """空 diff → 返回空集合，skip_reason 为 None"""
    mgr = _make_manager()
    diff = ConfigDiff()

    components = mgr.decide_components(diff)

    assert components == set()
    assert mgr._skip_reason is None


# --------------------------------------------------------------------------- #
# 测试用例 5：单组件失败时其他组件仍执行（隔离）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_reinit_single_failure_isolated():
    """mock reinit_component 让 model_router 失败，验证其他组件仍执行。

    构造：components = {model_router, llm_client, context_manager}
    mock model_router 抛 RuntimeError，其他两个成功。
    预期：
        - affected = ["llm_client", "context_manager"]（按依赖顺序）
        - failed = ["model_router"]
        - errors["model_router"] 包含 "RuntimeError"
        - success = False
        - partial = True
    """
    mgr = _make_manager()

    # 记录调用顺序
    call_log = []

    async def fake_reinit_component(name: str) -> None:
        call_log.append(name)
        if name == "model_router":
            raise RuntimeError("mock model_router failure")
        # 其他组件正常完成（不抛异常）

    # monkeypatch 替换 reinit_component
    mgr.reinit_component = fake_reinit_component  # type: ignore[assignment]

    components: Set[str] = {"model_router", "llm_client", "context_manager"}
    result = await mgr.reinit(components=components)

    # 验证：失败的组件不影响后续组件执行
    assert "model_router" in result.failed
    assert "llm_client" in result.affected
    assert "context_manager" in result.affected
    assert result.success is False
    assert result.partial is True
    assert "model_router" in result.errors
    assert "RuntimeError" in result.errors["model_router"]
    # 调用顺序符合依赖顺序
    assert call_log == ["model_router", "llm_client", "context_manager"]


# --------------------------------------------------------------------------- #
# 测试用例 6：get_status 无任务时返回 idle
# --------------------------------------------------------------------------- #


def test_get_status_idle():
    """无任务时返回 {"status": "idle", "last_result": None, "last_at": None}"""
    mgr = _make_manager()

    status = mgr.get_status()

    assert status["status"] == "idle"
    assert status["last_result"] is None
    assert status["last_at"] is None


# --------------------------------------------------------------------------- #
# 补充：get_status 在 reinit 完成后记录 last_result
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_status_after_reinit_records_last_result():
    """reinit 完成后 get_status 返回 last_result。"""
    mgr = _make_manager()

    async def fake_reinit_component(name: str) -> None:
        pass

    mgr.reinit_component = fake_reinit_component  # type: ignore[assignment]

    result = await mgr.reinit(components={"llm_client"})
    status = mgr.get_status()

    assert status["status"] == "idle"
    assert status["last_result"] is not None
    assert "llm_client" in status["last_result"]["affected"]
    assert status["last_at"] == result.finished_at


# --------------------------------------------------------------------------- #
# 补充：reinit with diff=database 走 skipped 路径
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_reinit_with_database_diff_returns_skipped():
    """reinit(diff={database}) → result.skipped=True, errors 含 database"""
    mgr = _make_manager()
    diff = ConfigDiff(
        changed_sections={"database"},
        field_changes=["database.path"],
    )

    result = await mgr.reinit(diff=diff)

    assert result.skipped is True
    assert result.success is False
    assert "database" in result.errors
    assert "requires process restart" in result.errors["database"]
    assert result.affected == []


# --------------------------------------------------------------------------- #
# 补充：reinit with pure_param diff 走 skipped 路径（success=True）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_reinit_with_pure_param_diff_returns_skipped_success():
    """reinit(diff={pure_param}) → result.skipped=True, success=True"""
    mgr = _make_manager()
    diff = ConfigDiff(
        changed_sections={"memory"},
        field_changes=["memory.dedup_threshold"],
    )

    result = await mgr.reinit(diff=diff)

    assert result.skipped is True
    assert result.success is True
    assert result.affected == []


# --------------------------------------------------------------------------- #
# 补充：ReinitResult.partial 属性
# --------------------------------------------------------------------------- #


def test_reinit_result_partial_property():
    """ReinitResult.partial 在 failed 非空时为 True"""
    r1 = ReinitResult()
    assert r1.partial is False

    r2 = ReinitResult(failed=["model_router"])
    assert r2.partial is True


# --------------------------------------------------------------------------- #
# 补充：reinit 重入保护（M8-a）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_reinit_rejects_concurrent_call():
    """上一次 reinit 进行中时，再次调用被拒绝（success=False + 原因）。

    构造：
        - reinit_component 用慢速 mock 挂起，第一个 reinit 保持 running
        - 第二个 reinit 调用应立即被拒绝，不等待
    验证：
        - 进行中 get_status 返回 running（由 _reinit_in_progress 驱动）
        - 第二次调用 success=False，errors["reinit"] 说明原因
        - 第一个 reinit 完成后标志复位，get_status 恢复 idle
    """
    mgr = _make_manager()

    release = asyncio.Event()

    async def slow_reinit_component(name: str) -> None:
        # 模拟慢速 reinit：挂起直到测试放行
        await release.wait()

    mgr.reinit_component = slow_reinit_component  # type: ignore[assignment]

    first = asyncio.create_task(mgr.reinit(components={"llm_client"}))
    # 让第一个 reinit 进入执行并挂起
    await asyncio.sleep(0.05)

    assert mgr.get_status()["status"] == "running"

    second = await mgr.reinit(components={"llm_client"})
    assert second.success is False
    assert "another reinit is in progress" in second.errors["reinit"]

    # 放行第一个 reinit 并确认最终状态复位
    release.set()
    result = await first
    assert result.success is True

    status = mgr.get_status()
    assert status["status"] == "idle"
    assert status["last_result"] is not None
