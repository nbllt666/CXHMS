"""模块7_模板引擎（TemplateEngine）。

RADIX-Lite 子系统之一：YAML frontmatter + Jinja2 原生渲染的进程内模板引擎。

对应契约:
- 接口契约: public/interface_stub/template_engine.pyi
- 数据契约: public/schema/template_registry.schema.json
- 配置契约: public/config_template/radix_config.json (template_engine 段)

公开导出:
- TemplateEngine            — 模板引擎主类
- TemplateFrontmatter       — frontmatter 解析结果模型
- TemplateRecord            — 模板记录模型
- RenderResult              — 渲染结果模型
- CreateTemplateRequest     — 创建模板请求模型
- UpdateTemplateRequest     — 更新模板请求模型

@version 1.0.0
"""

from modules.模块7_模板引擎.template_engine import (
    CreateTemplateRequest,
    RenderResult,
    TemplateEngine,
    TemplateFrontmatter,
    TemplateRecord,
    UpdateTemplateRequest,
)

__all__ = [
    "TemplateEngine",
    "TemplateFrontmatter",
    "TemplateRecord",
    "RenderResult",
    "CreateTemplateRequest",
    "UpdateTemplateRequest",
]

__version__ = "1.0.0"
