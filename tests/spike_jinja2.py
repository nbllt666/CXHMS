"""Jinja2 自定义扩展最小可行性验证（spike）。

GN-004 观察项 3 要求：在 S2 契约冻结阶段验证 Jinja2 自定义扩展可行性。
方案 C 原设计使用 {% meta %} Jinja2 自定义标签。
本 spike 验证：YAML frontmatter + Jinja2 原生渲染（extends/block/if/for）是否可行。
"""
import re
import yaml
from jinja2 import Environment, BaseLoader, DictLoader


def test_yaml_frontmatter_parsing():
    """验证 YAML frontmatter 解析。"""
    template_content = """---
workflow_mode: "multi_turn"
expected_turns: 4
required_vars:
  - source_type
  - preread_summary
---

{% block system %}
You are a distillation agent. Source type: {{ source_type }}.
{% if source_type == "character_card" %}
Focus: persona, relations, scenario, dialogue style.
{% elif source_type == "text" %}
Focus: facts, concepts, causal chains.
{% endif %}
{% endblock %}

{% for turn in history %}
[Turn {{ loop.index }}] User: {{ turn.user }}
{% endfor %}

{% if confidence < 0.6 %}
Low confidence {{ confidence }}, suggest cross_validate.
{% else %}
Ready for extract phase.
{% endif %}
"""
    fm_match = re.match(r'^---\n(.*?)\n---\n(.*)$', template_content, re.DOTALL)
    assert fm_match, "YAML frontmatter regex failed"
    meta = yaml.safe_load(fm_match.group(1))
    body = fm_match.group(2)
    assert meta["workflow_mode"] == "multi_turn"
    assert meta["expected_turns"] == 4
    assert "source_type" in meta["required_vars"]
    print("[PASS] YAML frontmatter parsing")
    return body


def test_jinja2_native_rendering(body):
    """验证 Jinja2 原生 if/for/block 渲染。"""
    env = Environment(loader=BaseLoader())
    template = env.from_string(body)
    rendered = template.render(
        source_type="character_card",
        confidence=0.4,
        history=[{"user": "What is this?"}, {"user": "Tell me more"}],
    )
    assert "distillation agent" in rendered
    assert "persona, relations" in rendered
    assert "[Turn 1]" in rendered
    assert "[Turn 2]" in rendered
    assert "Low confidence 0.4" in rendered
    print("[PASS] Jinja2 native rendering (if/elif/for/block)")


def test_jinja2_extends_inheritance():
    """验证 Jinja2 extends/block 继承。"""
    parent = "{% block system %}default system{% endblock %} | {% block body %}default body{% endblock %}"
    child = '{% extends "parent.j2" %}{% block body %}overridden body{% endblock %}'
    env = Environment(loader=DictLoader({"parent.j2": parent, "child.j2": child}))
    t = env.get_template("child.j2")
    rendered = t.render()
    assert "default system" in rendered
    assert "overridden body" in rendered
    assert "default body" not in rendered
    print("[PASS] Jinja2 extends/block inheritance")


def test_jinja2_include_composition():
    """验证 Jinja2 include 组合。"""
    module = "Reflection module content"
    main = '{% include "reflection.j2" %} + main content'
    env = Environment(loader=DictLoader({"reflection.j2": module, "main.j2": main}))
    t = env.get_template("main.j2")
    rendered = t.render()
    assert "Reflection module content" in rendered
    assert "main content" in rendered
    print("[PASS] Jinja2 include composition")


def test_custom_filter():
    """验证自定义过滤器（confidence_label）。"""
    env = Environment(loader=BaseLoader())

    def confidence_label(value):
        if value < 0.4:
            return "low"
        elif value < 0.7:
            return "medium"
        else:
            return "high"

    env.filters["confidence_label"] = confidence_label
    template = env.from_string("Confidence: {{ confidence | confidence_label }}")
    assert template.render(confidence=0.3) == "Confidence: low"
    assert template.render(confidence=0.5) == "Confidence: medium"
    assert template.render(confidence=0.8) == "Confidence: high"
    print("[PASS] Custom filter (confidence_label)")


if __name__ == "__main__":
    print("=== Jinja2 Spike: YAML frontmatter + native rendering ===")
    body = test_yaml_frontmatter_parsing()
    test_jinja2_native_rendering(body)
    test_jinja2_extends_inheritance()
    test_jinja2_include_composition()
    test_custom_filter()
    print("\n=== SPIKE CONCLUSION ===")
    print("YAML frontmatter + Jinja2 native (if/for/extends/block/include/filter) all work.")
    print("Decision: Replace {% meta %} custom tag with YAML frontmatter.")
    print("No Jinja2 custom Extension needed. Use native extends/block/if/for/include.")
