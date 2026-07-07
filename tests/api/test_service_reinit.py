"""backend.api.routers.service 的 API 集成测试（Task 5）。

覆盖新增的 3 个端点与修改的 /service/config：
    1. POST /api/service/reload-config
    2. POST /api/service/reinit
    3. GET  /api/service/reinit/status
    4. POST /api/service/config（接入 auto_reinit）

测试策略：
    - 复用 conftest.sim_app fixture（CXHMS_SIMULATION=1 触发模拟 lifespan，
      装配 ServiceState 与 fakes）
    - 手动注入 mock ReinitManager 到 app.state.reinit_manager
    - mock config.settings.settings.reload_config_with_diff 控制返回 diff
    - 用 monkeypatch.chdir 切换到 tmp_path，避免 update_service_config 写入
      真实 config/default.yaml
    - 用自定义 MockReinitManager（轻量 mock，避免 MagicMock 异步方法签名问题）
"""

import os
from typing import Any, Dict, List, Optional, Set

import pytest

from backend.core.config.diff import ConfigDiff


# --------------------------------------------------------------------------- #
# 辅助：轻量 Mock ReinitManager
# --------------------------------------------------------------------------- #


class MockReinitManager:
    """轻量 mock ReinitManager。

    模拟真实 ReinitManager 的对外接口：
        - get_status() -> Dict
        - decide_components(diff) -> Set[str]
        - reinit(components, diff) -> ReinitResult（async）
        - REINIT_ORDER 类属性
        - _current_task 实例属性

    通过设置 status_mode 控制返回 running / idle。
    通过 reinit_components_outcome 控制返回的组件集合。
    """

    REINIT_ORDER: List[str] = [
        "model_router",
        "llm_client",
        "memory_manager",
        "context_manager",
        "secondary_router",
        "acp_manager",
        "cxfc_manager",
    ]

    def __init__(
        self,
        status_mode: str = "idle",
        decide_components_set: Optional[Set[str]] = None,
    ) -> None:
        self.status_mode = status_mode  # "idle" or "running"
        self._decide_components_set = decide_components_set  # decide_components 返回
        self._current_component: Optional[str] = None
        self._current_task: Any = None
        self._last_result: Optional[Dict[str, Any]] = None
        self._last_at: Optional[str] = None
        # 记录 reinit 被调用的参数
        self.reinit_calls: List[Dict[str, Any]] = []

    def get_status(self) -> Dict[str, Any]:
        if self.status_mode == "running":
            return {
                "status": "running",
                "current_component": "memory_manager",
                "progress": "1/7",
            }
        return {
            "status": "idle",
            "last_result": self._last_result,
            "last_at": self._last_at,
        }

    def decide_components(self, diff: ConfigDiff) -> Set[str]:
        if self._decide_components_set is not None:
            return self._decide_components_set
        # 默认按 diff 的 changed_sections 映射
        if diff is None or diff.is_empty():
            return set()
        # 简单映射：models → {model_router, llm_client}
        mapping = {
            "models": {"model_router", "llm_client"},
            "llm": {"model_router", "llm_client"},
            "memory": {"memory_manager"},
            "vector": {"memory_manager"},
        }
        result: Set[str] = set()
        for section in diff.changed_sections:
            result |= mapping.get(section, set())
        return result

    async def reinit(
        self,
        components: Optional[Set[str]] = None,
        diff: Optional[ConfigDiff] = None,
    ):
        """模拟 reinit：记录调用，返回简化的 result dict。

        注意：真实 ReinitManager.reinit 返回 ReinitResult dataclass；
        这里返回 dict 是为了在 get_status 的 last_result 中可序列化。
        测试不依赖 ReinitResult 的具体结构。
        """
        self.reinit_calls.append({"components": components, "diff": diff})
        result = {
            "affected": list(components) if components else [],
            "failed": [],
            "success": True,
            "skipped": False,
            "errors": {},
            "warnings": [],
            "started_at": "2026-07-07T00:00:00",
            "finished_at": "2026-07-07T00:00:01",
        }
        self._last_result = result
        self._last_at = result["finished_at"]
        # 模拟任务完成：清空 _current_task
        self._current_task = None
        return result


# --------------------------------------------------------------------------- #
# 辅助：模拟 ReinitResult（用于 status 测试）
# --------------------------------------------------------------------------- #


def _make_diff(changed: Set[str], fields: List[str]) -> ConfigDiff:
    """构造 ConfigDiff 实例。"""
    return ConfigDiff(changed_sections=changed, field_changes=fields)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def mock_reinit_manager():
    """提供 MockReinitManager 实例（默认 idle 模式）。"""
    return MockReinitManager(status_mode="idle")


@pytest.fixture
def inject_reinit_manager(sim_app, mock_reinit_manager):
    """将 mock ReinitManager 注入到 sim_app 的 app.state。

    sim_app 的 lifespan 不会挂载 reinit_manager（Task 5 仅完成 API 层，
    未在 lifespan 中挂载），故由测试显式注入。

    teardown：移除注入，避免污染其他测试。
    """
    sim_app.app.state.reinit_manager = mock_reinit_manager
    yield mock_reinit_manager
    # teardown
    if hasattr(sim_app.app.state, "reinit_manager"):
        del sim_app.app.state.reinit_manager


@pytest.fixture
def isolated_workdir(monkeypatch, tmp_path):
    """切换工作目录到 tmp_path，并创建 config/default.yaml 空文件。

    避免 update_service_config 写入真实 config/default.yaml。
    """
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    # 创建空 YAML 文件（update_service_config 会读取并合并）
    (config_dir / "default.yaml").write_text("", encoding="utf-8")
    return tmp_path


def _patch_reload_diff(monkeypatch, diff: Optional[ConfigDiff]):
    """patch settings.reload_config_with_diff 返回指定 diff。"""
    from config.settings import settings

    def _fake_reload(self_or_path=None):
        return diff

    # reload_config_with_diff 是 bound method，直接替换实例属性
    monkeypatch.setattr(settings, "reload_config_with_diff", _fake_reload)
    return _fake_reload


# --------------------------------------------------------------------------- #
# 测试用例 1：POST /api/service/reload-config
# --------------------------------------------------------------------------- #


def test_reload_config(sim_app, monkeypatch):
    """POST /api/service/reload-config 应返回 status=success 与 diff。"""
    diff = _make_diff({"models"}, ["models.main.model"])
    _patch_reload_diff(monkeypatch, diff)

    response = sim_app.post("/api/service/reload-config")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["diff"] is not None
    assert "models" in body["diff"]["changed_sections"]
    assert "models.main.model" in body["diff"]["field_changes"]


# --------------------------------------------------------------------------- #
# 测试用例 2：POST /api/service/reinit 返回 202 accepted
# --------------------------------------------------------------------------- #


def test_reinit_accepted(sim_app, inject_reinit_manager):
    """POST /api/service/reinit body {components: [...]} → 202 accepted + task_id。"""
    response = sim_app.post(
        "/api/service/reinit", json={"components": ["model_router"]}
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert "task_id" in body
    assert body["task_id"]  # 非空
    assert "model_router" in body["estimated_components"]
    # diff 为 None（未 reload_first）
    assert body["diff"] is None

    # 验证 reinit 被异步触发（mock 立即完成）
    assert len(inject_reinit_manager.reinit_calls) == 1
    call = inject_reinit_manager.reinit_calls[0]
    assert call["components"] == {"model_router"}


# --------------------------------------------------------------------------- #
# 测试用例 3：POST /api/service/reinit 返回 409 conflict
# --------------------------------------------------------------------------- #


def test_reinit_conflict(sim_app, mock_reinit_manager):
    """reinit_manager.get_status 返回 running 时 POST /api/service/reinit → 409。"""
    mock_reinit_manager.status_mode = "running"
    sim_app.app.state.reinit_manager = mock_reinit_manager

    try:
        response = sim_app.post(
            "/api/service/reinit", json={"components": ["model_router"]}
        )

        assert response.status_code == 409
        body = response.json()
        assert body["status"] == "conflict"
        assert "in progress" in body["message"]
        assert body["current_component"] == "memory_manager"
        # 不应触发 reinit
        assert len(mock_reinit_manager.reinit_calls) == 0
    finally:
        if hasattr(sim_app.app.state, "reinit_manager"):
            del sim_app.app.state.reinit_manager


# --------------------------------------------------------------------------- #
# 测试用例 4：GET /api/service/reinit/status
# --------------------------------------------------------------------------- #


def test_reinit_status(sim_app, inject_reinit_manager):
    """GET /api/service/reinit/status 应返回 reinit_manager.get_status() 的内容。"""
    # 设置一些 last_result / last_at
    inject_reinit_manager._last_result = {
        "affected": ["model_router"],
        "failed": [],
        "success": True,
    }
    inject_reinit_manager._last_at = "2026-07-07T00:00:01"

    response = sim_app.get("/api/service/reinit/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "idle"
    assert body["last_result"] is not None
    assert body["last_result"]["affected"] == ["model_router"]
    assert body["last_at"] == "2026-07-07T00:00:01"


def test_reinit_status_running(sim_app, mock_reinit_manager):
    """get_status 返回 running 时 GET /api/service/reinit/status → running 状态。"""
    mock_reinit_manager.status_mode = "running"
    sim_app.app.state.reinit_manager = mock_reinit_manager

    try:
        response = sim_app.get("/api/service/reinit/status")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "running"
        assert body["current_component"] == "memory_manager"
        assert body["progress"] == "1/7"
    finally:
        if hasattr(sim_app.app.state, "reinit_manager"):
            del sim_app.app.state.reinit_manager


# --------------------------------------------------------------------------- #
# 测试用例 5：POST /api/service/config with auto_reinit=true
# --------------------------------------------------------------------------- #


def test_config_save_with_auto_reinit(
    sim_app, inject_reinit_manager, isolated_workdir, monkeypatch
):
    """auto_reinit=true → 保存 YAML + 异步触发 reinit + 返回 diff + reinit_task_id。"""
    diff = _make_diff({"models"}, ["models.main.model"])
    _patch_reload_diff(monkeypatch, diff)

    response = sim_app.post(
        "/api/service/config",
        json={
            "models": {
                "main": {
                    "provider": "ollama",
                    "host": "http://localhost:11434",
                    "model": "llama3.2:3b",
                }
            },
            "auto_reinit": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    # 应返回 accepted 状态（含 diff 与 reinit_task_id）
    assert body["status"] == "accepted"
    assert "diff" in body
    assert body["diff"] is not None
    assert "models" in body["diff"]["changed_sections"]
    assert "reinit_task_id" in body
    assert body["reinit_task_id"]
    assert "estimated_components" in body
    # 验证 reinit 被触发
    assert len(inject_reinit_manager.reinit_calls) == 1
    call = inject_reinit_manager.reinit_calls[0]
    # decide_components 返回的组件应包含 model_router / llm_client
    assert "model_router" in call["components"]
    assert "llm_client" in call["components"]


# --------------------------------------------------------------------------- #
# 测试用例 6：POST /api/service/config with auto_reinit=false
# --------------------------------------------------------------------------- #


def test_config_save_without_auto_reinit(
    sim_app, inject_reinit_manager, isolated_workdir
):
    """auto_reinit=false → 仅保存 YAML，不触发 reinit，返回 manual reinit required。"""
    response = sim_app.post(
        "/api/service/config",
        json={
            "models": {
                "main": {
                    "provider": "ollama",
                    "host": "http://localhost:11434",
                    "model": "llama3.2:3b",
                }
            },
            "auto_reinit": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert "manual reinit required" in body["message"]
    # 不应触发 reinit
    assert len(inject_reinit_manager.reinit_calls) == 0


# --------------------------------------------------------------------------- #
# 补充：reload-config 失败时返回 500
# --------------------------------------------------------------------------- #


def test_reload_config_failure(sim_app, monkeypatch):
    """reload_config_with_diff 抛异常 → 500。

    注意：app.py 注册了自定义 http_exception_handler，返回 ErrorResponse 格式
    {"error": ..., "error_code": "HTTP_500"}，而非 FastAPI 默认的 {"detail": ...}。
    """
    from config.settings import settings

    def _raising_reload(self_or_path=None):
        raise RuntimeError("yaml parse error")

    monkeypatch.setattr(settings, "reload_config_with_diff", _raising_reload)

    response = sim_app.post("/api/service/reload-config")

    assert response.status_code == 500
    body = response.json()
    # ErrorResponse 格式：{"error": ..., "error_code": "HTTP_500"}
    assert "重载失败" in body["error"]
    assert body["error_code"] == "HTTP_500"


# --------------------------------------------------------------------------- #
# 补充：reinit_manager 未挂载时返回 503
# --------------------------------------------------------------------------- #


def test_reinit_unavailable(sim_app):
    """app.state.reinit_manager 未挂载 → 503。"""
    # 确保没有 reinit_manager（sim_app 默认不挂载）
    if hasattr(sim_app.app.state, "reinit_manager"):
        del sim_app.app.state.reinit_manager

    response = sim_app.post("/api/service/reinit", json={"components": ["model_router"]})
    assert response.status_code == 503


def test_reinit_status_unavailable(sim_app):
    """app.state.reinit_manager 未挂载 → GET status 返回 503。"""
    if hasattr(sim_app.app.state, "reinit_manager"):
        del sim_app.app.state.reinit_manager

    response = sim_app.get("/api/service/reinit/status")
    assert response.status_code == 503


# --------------------------------------------------------------------------- #
# 补充：reinit with reload_first=True
# --------------------------------------------------------------------------- #


def test_reinit_with_reload_first(sim_app, inject_reinit_manager, monkeypatch):
    """reload_first=true → 先 reload 配置，再由 diff 决策组件。"""
    diff = _make_diff({"models"}, ["models.main.model"])
    _patch_reload_diff(monkeypatch, diff)

    response = sim_app.post("/api/service/reinit", json={"reload_first": True})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["diff"] is not None
    assert "models" in body["diff"]["changed_sections"]
    # 由 decide_components 决策 → {model_router, llm_client}
    assert "model_router" in body["estimated_components"]
    assert "llm_client" in body["estimated_components"]


# --------------------------------------------------------------------------- #
# 补充：reinit 决策出空集合 → skipped
# --------------------------------------------------------------------------- #


def test_reinit_skipped_empty_components(sim_app, inject_reinit_manager, monkeypatch):
    """reload_first=true 但 diff 为空 → decide_components 返回空集合 → skipped。"""
    diff = _make_diff(set(), [])
    _patch_reload_diff(monkeypatch, diff)

    response = sim_app.post("/api/service/reinit", json={"reload_first": True})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert "no components need reinit" in body["message"]
    assert body["result"]["skipped"] is True
    # 不应触发 reinit
    assert len(inject_reinit_manager.reinit_calls) == 0
