"""TemplateEngine 实例化冒烟测试。

验证 Task 2 闭合判据（tasks.md）:
- render_template 返回 RenderResult 含 3 字段
- list_templates 返回非空列表
- get_template 返回 TemplateRecord
- create_template + delete_template CRUD 闭环

测试策略:
- 用 tmp_path 隔离测试环境，不污染真实 data/templates/
- 验证 auto_init 创建默认预设模板（default + distillation）
- 验证 Jinja2 真实渲染（if/for/filter/extends）
- 验证异常路径（KeyError / ValueError / PermissionError / FileExistsError）
"""

import os
import sys

import pytest

# 项目根加入 sys.path（与 tests/conftest.py 一致）
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from modules.模块7_模板引擎 import (  # noqa: E402
    CreateTemplateRequest,
    RenderResult,
    TemplateEngine,
    TemplateFrontmatter,
    TemplateRecord,
    UpdateTemplateRequest,
)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def engine(tmp_path) -> TemplateEngine:
    """提供隔离的 TemplateEngine 实例（tmp_path 避免污染真实 data/templates/）。"""
    templates_dir = os.path.join(str(tmp_path), "templates")
    return TemplateEngine(
        templates_dir=templates_dir,
        presets_dir=os.path.join(templates_dir, "presets"),
        custom_dir=os.path.join(templates_dir, "custom"),
    )


# --------------------------------------------------------------------------- #
# 1. auto_init 验证
# --------------------------------------------------------------------------- #


def test_auto_init_creates_default_presets(engine: TemplateEngine):
    """auto_init 后 presets/ 应含 default.j2 和 distillation.j2。"""
    assert os.path.isfile(os.path.join(engine.presets_dir, "default.j2"))
    assert os.path.isfile(os.path.join(engine.presets_dir, "distillation.j2"))
    assert os.path.isdir(engine.custom_dir)


# --------------------------------------------------------------------------- #
# 2. render_template 返回 RenderResult 含 3 字段
# --------------------------------------------------------------------------- #


def test_render_template_returns_render_result_with_3_fields(engine: TemplateEngine):
    """render_template 返回 RenderResult，含 rendered_prompt / workflow_definition / expected_turns。"""
    result = engine.render_template(
        template_id="default",
        variables={"content": "Hello world", "context": "extra ctx"},
    )
    assert isinstance(result, RenderResult)
    # 3 字段全部存在
    assert hasattr(result, "rendered_prompt")
    assert hasattr(result, "workflow_definition")
    assert hasattr(result, "expected_turns")
    # 渲染结果含输入内容
    assert "Hello world" in result.rendered_prompt
    assert "extra ctx" in result.rendered_prompt
    # workflow_definition 含 workflow_mode + expected_turns
    assert result.workflow_definition["workflow_mode"] == "single_turn"
    assert result.workflow_definition["expected_turns"] == 1
    assert result.expected_turns == 1


def test_render_template_jinja2_native_features(engine: TemplateEngine):
    """验证 Jinja2 原生 if/for/filter 渲染（distillation 模板）。"""
    result = engine.render_template(
        template_id="distillation",
        variables={
            "source_type": "character_card",
            "source_ref": "chara.png",
            "preread_summary": "A persona card.",
            "history": [
                {"user": "What is this?"},
                {"user": "Tell me more"},
            ],
            "confidence": 0.3,
        },
    )
    # if 分支生效
    assert "A persona card." in result.rendered_prompt
    # for 循环生效
    assert "[Turn 1]" in result.rendered_prompt
    assert "[Turn 2]" in result.rendered_prompt
    # 自定义 filter confidence_label 生效（0.3 < 0.4 → "低"）
    assert "低" in result.rendered_prompt
    # if confidence < 0.6 分支生效
    assert "Low confidence" in result.rendered_prompt
    # expected_turns 来自 frontmatter
    assert result.expected_turns == 4
    assert result.workflow_definition["workflow_mode"] == "multi_turn"


def test_render_template_missing_required_vars_raises(engine: TemplateEngine):
    """render_template 缺少 required_vars raise ValueError（422）。"""
    with pytest.raises(ValueError, match="required_vars"):
        engine.render_template(
            template_id="default",
            variables={},  # 缺 content
        )


def test_render_template_not_found_raises(engine: TemplateEngine):
    """render_template 不存在的 template_id raise KeyError（404）。"""
    with pytest.raises(KeyError):
        engine.render_template(
            template_id="nonexistent_template",
            variables={"content": "x"},
        )


def test_render_template_workflow_mode_override(engine: TemplateEngine):
    """workflow_mode 覆盖参数生效。"""
    result = engine.render_template(
        template_id="default",
        variables={"content": "x"},
        workflow_mode="multi_turn",
    )
    assert result.workflow_definition["workflow_mode"] == "multi_turn"


def test_render_template_invalid_workflow_mode_raises(engine: TemplateEngine):
    """workflow_mode 无效值 raise ValueError（422）。"""
    with pytest.raises(ValueError, match="workflow_mode"):
        engine.render_template(
            template_id="default",
            variables={"content": "x"},
            workflow_mode="invalid_mode",
        )


# --------------------------------------------------------------------------- #
# 3. list_templates 返回非空列表
# --------------------------------------------------------------------------- #


def test_list_templates_returns_non_empty(engine: TemplateEngine):
    """list_templates 返回非空列表（auto_init 后至少 2 个 preset）。"""
    records = engine.list_templates()
    assert isinstance(records, list)
    assert len(records) >= 2
    # 按 template_id 升序
    ids = [r.template_id for r in records]
    assert ids == sorted(ids)


def test_list_templates_filter_preset(engine: TemplateEngine):
    """list_templates(category='preset') 仅返回 preset。"""
    records = engine.list_templates(category="preset")
    assert len(records) >= 2
    assert all(r.category == "preset" for r in records)


def test_list_templates_filter_custom_empty(engine: TemplateEngine):
    """list_templates(category='custom') 在无自定义模板时返回空列表。"""
    records = engine.list_templates(category="custom")
    assert records == []


def test_list_templates_invalid_category_raises(engine: TemplateEngine):
    """list_templates 非法 category raise ValueError（422）。"""
    with pytest.raises(ValueError, match="category"):
        engine.list_templates(category="invalid")


# --------------------------------------------------------------------------- #
# 4. get_template 返回 TemplateRecord
# --------------------------------------------------------------------------- #


def test_get_template_returns_record(engine: TemplateEngine):
    """get_template 返回 TemplateRecord，字段完整。"""
    record = engine.get_template("default")
    assert isinstance(record, TemplateRecord)
    assert record.template_id == "default"
    assert record.category == "preset"
    assert isinstance(record.frontmatter, TemplateFrontmatter)
    assert record.frontmatter.workflow_mode == "single_turn"
    assert record.frontmatter.expected_turns == 1
    assert "content" in record.frontmatter.required_vars
    assert record.body  # body 非空
    assert record.file_path is not None
    assert record.file_path.endswith("default.j2")


def test_get_template_not_found_raises(engine: TemplateEngine):
    """get_template 不存在 raise KeyError（404）。"""
    with pytest.raises(KeyError):
        engine.get_template("nonexistent")


# --------------------------------------------------------------------------- #
# 5. create_template + delete_template CRUD 闭环
# --------------------------------------------------------------------------- #


def test_create_and_delete_template_crud(engine: TemplateEngine):
    """create_template + delete_template CRUD 闭环。"""
    # 创建
    request = CreateTemplateRequest(
        template_id="my-custom",
        name="我的自定义模板",
        frontmatter=TemplateFrontmatter(
            workflow_mode="single_turn",
            expected_turns=1,
            required_vars=["topic"],
            optional_vars=[],
            extends=None,
            description="测试自定义模板",
        ),
        body="请总结以下主题：{{ topic }}",
    )
    record = engine.create_template(request)
    assert isinstance(record, TemplateRecord)
    assert record.template_id == "my-custom"
    assert record.category == "custom"
    # 文件已写入
    assert os.path.isfile(os.path.join(engine.custom_dir, "my-custom.j2"))

    # get_template 能查到
    fetched = engine.get_template("my-custom")
    assert fetched.template_id == "my-custom"
    assert fetched.category == "custom"

    # list_templates category=custom 包含
    custom_list = engine.list_templates(category="custom")
    assert any(r.template_id == "my-custom" for r in custom_list)

    # 渲染新创建的模板
    result = engine.render_template(
        template_id="my-custom",
        variables={"topic": "AI 蒸馏"},
    )
    assert "AI 蒸馏" in result.rendered_prompt

    # 删除
    deleted = engine.delete_template("my-custom")
    assert deleted is True
    # 文件已物理删除
    assert not os.path.isfile(os.path.join(engine.custom_dir, "my-custom.j2"))

    # 删除后 get_template raise KeyError
    with pytest.raises(KeyError):
        engine.get_template("my-custom")


def test_create_template_duplicate_raises(engine: TemplateEngine):
    """create_template 已存在的 template_id raise FileExistsError（409）。"""
    request = CreateTemplateRequest(
        template_id="default",  # 已存在 preset
        name="覆盖默认",
        frontmatter=TemplateFrontmatter(
            workflow_mode="single_turn",
            expected_turns=1,
        ),
        body="body",
    )
    with pytest.raises(FileExistsError):
        engine.create_template(request)


def test_create_template_invalid_id_raises(engine: TemplateEngine):
    """create_template 非法 template_id raise ValueError（422）。"""
    request = CreateTemplateRequest(
        template_id="invalid/id",  # 含非法字符
        name="非法 ID",
        frontmatter=TemplateFrontmatter(
            workflow_mode="single_turn",
            expected_turns=1,
        ),
        body="body",
    )
    with pytest.raises(ValueError, match="template_id"):
        engine.create_template(request)


def test_delete_preset_raises_permission_error(engine: TemplateEngine):
    """delete_template 对 preset raise PermissionError（403）。"""
    with pytest.raises(PermissionError):
        engine.delete_template("default")


def test_delete_nonexistent_raises_key_error(engine: TemplateEngine):
    """delete_template 不存在 raise KeyError（404）。"""
    with pytest.raises(KeyError):
        engine.delete_template("nonexistent")


# --------------------------------------------------------------------------- #
# 6. update_template
# --------------------------------------------------------------------------- #


def test_update_template(engine: TemplateEngine):
    """update_template 更新 name/body/frontmatter。"""
    # 先创建
    create_req = CreateTemplateRequest(
        template_id="upd-test",
        name="原名",
        frontmatter=TemplateFrontmatter(
            workflow_mode="single_turn",
            expected_turns=1,
            required_vars=["x"],
        ),
        body="原 body {{ x }}",
    )
    engine.create_template(create_req)

    # 更新
    update_req = UpdateTemplateRequest(
        name="新名",
        body="新 body {{ x }} v2",
        frontmatter=TemplateFrontmatter(
            workflow_mode="multi_turn",
            expected_turns=2,
            required_vars=["x"],
        ),
    )
    updated = engine.update_template("upd-test", update_req)
    assert updated.name == "新名"
    assert "v2" in updated.body
    assert updated.frontmatter.workflow_mode == "multi_turn"
    assert updated.frontmatter.expected_turns == 2

    # 重新加载验证持久化
    fetched = engine.get_template("upd-test")
    assert fetched.name == "新名"
    assert "v2" in fetched.body


def test_update_preset_raises_permission_error(engine: TemplateEngine):
    """update_template 对 preset raise PermissionError（403）。"""
    with pytest.raises(PermissionError):
        engine.update_template("default", UpdateTemplateRequest(name="x"))


# --------------------------------------------------------------------------- #
# 7. _parse_frontmatter
# --------------------------------------------------------------------------- #


def test_parse_frontmatter_valid(engine: TemplateEngine):
    """_parse_frontmatter 解析合法 frontmatter。"""
    content = (
        "---\n"
        "workflow_mode: single_turn\n"
        "expected_turns: 2\n"
        "required_vars:\n"
        "  - a\n"
        "  - b\n"
        "---\n"
        "Body {{ a }} {{ b }}"
    )
    fm, body = engine._parse_frontmatter(content)
    assert fm.workflow_mode == "single_turn"
    assert fm.expected_turns == 2
    assert fm.required_vars == ["a", "b"]
    assert "Body" in body


def test_parse_frontmatter_missing_delimiter_raises(engine: TemplateEngine):
    """_parse_frontmatter 缺少 --- 分隔符 raise ValueError（422）。"""
    with pytest.raises(ValueError, match="frontmatter"):
        engine._parse_frontmatter("no frontmatter here")


def test_parse_frontmatter_missing_required_field_raises(engine: TemplateEngine):
    """_parse_frontmatter 缺少 workflow_mode raise ValueError（422）。"""
    content = "---\nexpected_turns: 1\n---\nbody"
    with pytest.raises(ValueError, match="workflow_mode"):
        engine._parse_frontmatter(content)


# --------------------------------------------------------------------------- #
# 8. extends 继承（spec.md Scenario: 模板继承）
# --------------------------------------------------------------------------- #


def test_template_extends_inheritance(tmp_path):
    """验证 Jinja2 extends/block 继承（spec.md Scenario: 模板继承）。"""
    templates_dir = os.path.join(str(tmp_path), "templates")
    engine = TemplateEngine(
        templates_dir=templates_dir,
        presets_dir=os.path.join(templates_dir, "presets"),
        custom_dir=os.path.join(templates_dir, "custom"),
    )

    # 创建父模板
    parent_req = CreateTemplateRequest(
        template_id="parent-base",
        name="父模板",
        frontmatter=TemplateFrontmatter(
            workflow_mode="single_turn",
            expected_turns=1,
        ),
        body=(
            "{% block system %}default system{% endblock %} | "
            "{% block body %}default body{% endblock %}"
        ),
    )
    engine.create_template(parent_req)

    # 创建子模板（extends parent-base）
    child_req = CreateTemplateRequest(
        template_id="child-extends",
        name="子模板",
        frontmatter=TemplateFrontmatter(
            workflow_mode="single_turn",
            expected_turns=1,
        ),
        body=(
            '{% extends "parent-base.j2" %}'
            "{% block body %}overridden body{% endblock %}"
        ),
    )
    engine.create_template(child_req)

    # 渲染子模板
    result = engine.render_template(
        template_id="child-extends",
        variables={},
    )
    # 父 system 块保留
    assert "default system" in result.rendered_prompt
    # 子 body 块覆盖
    assert "overridden body" in result.rendered_prompt
    # 父 body 块被覆盖，不再出现
    assert "default body" not in result.rendered_prompt
