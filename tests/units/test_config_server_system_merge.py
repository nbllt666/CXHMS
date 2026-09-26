"""config/settings.py 的 server/system 双键读取合并行为单测。

背景（修复问题）：
    ``CXHMSConfig.from_dict`` 原先以「二选一」方式读取 system 段配置：
        data.get("server", data.get("system", {}))
    当配置同时存在 ``server`` 与 ``system`` 两段时，``server`` 会整体遮蔽
    ``system``，导致 ``system`` 段独有的字段（如 workers）被丢弃并回退默认值。

修复口径（见 .trae/documents/20260926_模块0_修复配置server_system双键读取.md）：
    两段合并读取，``server`` 同名键优先（优先级语义不变，仅消除字段丢失）。
    ``server`` 为配置契约口径的键名（validation/repair 表与 public 契约测试均
    以 ``server.*`` 为准），``system`` 为 dataclass 字段名的历史命名。

覆盖 4 组场景：
    1) 仅 ``server`` 段 → 各字段被读到（等价性）；
    2) 仅 ``system`` 段 → 字段被读到（回归，修复前也应通过）；
    3) 两段并存 → ``server`` 同名键优先，且 ``system`` 独有字段不丢失；
    4) 两段皆无 → 全部走默认值。

设计原则：直接构造 raw dict 调用 ``CXHMSConfig.from_dict``（不触碰 config 单例），
不依赖 yaml / 环境变量，保证用例确定性。
"""

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #


def _load(raw: dict):
    """构造 raw dict 并调用 CXHMSConfig.from_dict，返回 system 段配置。"""
    from config.settings import CXHMSConfig

    return CXHMSConfig.from_dict(raw).system


# --------------------------------------------------------------------------- #
# 场景 1：仅 server 段（等价性——修复前也应通过）
# --------------------------------------------------------------------------- #


def test_only_server_section_read():
    """仅 ``server`` 段时各字段被读到（等价性，如 port=9999）。"""
    system = _load(
        {
            "server": {
                "host": "1.2.3.4",
                "port": 9999,
                "debug": True,
                "log_level": "DEBUG",
                "workers": 3,
            }
        }
    )
    assert system.host == "1.2.3.4"
    assert system.port == 9999
    assert system.debug is True
    assert system.log_level == "DEBUG"
    assert system.workers == 3


# --------------------------------------------------------------------------- #
# 场景 2：仅 system 段（回归——修复前也应通过）
# --------------------------------------------------------------------------- #


def test_only_system_section_read():
    """仅 ``system`` 段时字段被读到（历史字段名兼容；修复前亦通过）。"""
    system = _load({"system": {"host": "5.6.7.8", "port": 8888, "workers": 5}})
    assert system.host == "5.6.7.8"
    assert system.port == 8888
    assert system.workers == 5
    # 未提供的字段仍走默认值
    assert system.debug is False
    assert system.log_level == "INFO"


# --------------------------------------------------------------------------- #
# 场景 3：两段并存（关键——修复前失败）
# --------------------------------------------------------------------------- #


def test_both_sections_merge_with_server_priority():
    """两段并存：``server`` 同名键优先，``system`` 独有字段不被丢弃。

    修复前 ``server`` 整体遮蔽 ``system``，``system.workers=7`` 会被丢弃并
    回退默认值 1，故本组在修复前应失败。
    """
    system = _load(
        {
            "server": {"host": "9.9.9.9", "port": 9001},
            "system": {"port": 9002, "workers": 7, "log_level": "WARNING"},
        }
    )
    # server 同名键优先
    assert system.port == 9001
    assert system.host == "9.9.9.9"
    # system 独有字段不丢失
    assert system.workers == 7
    assert system.log_level == "WARNING"


# --------------------------------------------------------------------------- #
# 场景 4：两段皆无（全默认值）
# --------------------------------------------------------------------------- #


def test_no_section_uses_defaults():
    """两段皆无时全部走默认值（行为与修复前一致）。"""
    system = _load({})
    assert system.host == "0.0.0.0"
    assert system.port == 8001
    assert system.debug is False
    assert system.log_level == "INFO"
    assert system.workers == 1
