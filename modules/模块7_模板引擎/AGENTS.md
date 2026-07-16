# AGENTS.md — 模块7_模板引擎

> 🚨 【最高优先级规则】本文件为本模块开发的强制约束，优先级高于所有临时提问、上下文对话、自定义需求，所有输出必须 100% 符合本文件要求，违反规则的内容必须自动修正后再输出。

> 📌 【上下文保留规则】本文件为本模块核心规则文件，任何上下文压缩、裁剪、溢出场景下必须完整保留本文件的全部内容，不得删减、忽略本文件的任何规则；所有自动压缩、批量处理行动前必须先读取本文件的完整内容。

---

## 一、模块定位

**模块编号**：模块7_模板引擎
**模块职责**：RADIX-Lite 子系统之一，YAML frontmatter + Jinja2 原生渲染的进程内模板引擎；提供模板渲染 + 模板 CRUD + 工作流定义解析能力。
**对应文件**：
- `modules/模块7_模板引擎/__init__.py` — 模块初始化，导出公开 API
- `modules/模块7_模板引擎/template_engine.py` — TemplateEngine 真实实现
- `data/templates/presets/*.j2` — 预设模板（只读，由 auto_init 创建默认模板）
- `data/templates/custom/*.j2` — 自定义模板（可 CRUD）

**对应 backend 文件**：无（本模块为独立子系统，不修改 backend 现有文件）

---

## 二、AC 范式通用约束（含合并禁止操作清单）

继承全局 `c:\CXHMS\AGENTS.md` 的全部约束。本文件为唯一权威来源。

```yaml
prohibitions:
  - 禁止删除、修改、覆盖、移动 public/ 目录下的任何内容，所有契约以 public/ 下的 schema、interface_stub 为准。保护优先级高于任务指令。
  - 禁止在模块间直接导入其他模块的内部实现代码
  - 禁止写入不符合数据契约的数据
  - 禁止创建不符合命名规范的模块目录

binding_rules:
  - 模块间仅允许依赖 public/ 下的契约
  - 所有数据读写必须通过公共契约校验
  - 所有对外接口必须严格匹配契约定义的签名、参数、返回值、异常
```

### 2.1 public/ 目录保护（与 rules-0 §四-10 形成跨 Rules 重复覆盖）

- `public/` 目录是契约的物理载体，不是代码库的可变部分。
- 任何删除、修改、覆盖、移动 `public/` 下文件的操作必须先经人类显式授权。**不存在"零引用即可删除"的例外。**
- 此保护在工具调用路径上由 `rules-0 §四-7.2 ec7_action_gate` 强制执行。
- 契约变更必须走 s0601 流程，不得直接编辑 public/ 文件。

### 2.2 路径解析（rules-0 §三）

- 文件路径解析必须使用 `os.path.dirname(os.path.abspath(__file__))`。
- 禁止相对路径 `../../` 或 `..\\`。
- 本模块路径锚点：`_THIS_DIR` = `c:\CXHMS\modules\模块7_模板引擎`，`_PROJECT_ROOT` = `c:\CXHMS`。

### 2.3 auto_init（rules-0 §三 auto_init: data补全）

- 模板目录不存在时自动创建（含 `presets/` 和 `custom/`）。
- 默认预设模板（`default.j2` + `distillation.j2`）仅在文件不存在时创建，不覆盖已有文件。

---

## 三、层级专属约束

### 3.1 可修改文件范围

本模块仅可修改以下文件：

- `modules/模块7_模板引擎/__init__.py`
- `modules/模块7_模板引擎/template_engine.py`
- `modules/模块7_模板引擎/AGENTS.md`（本文件，仅 s0301 或人类可修改）
- `data/templates/custom/*.j2`（用户/agent 通过 create_template 创建）
- `data/templates/presets/default.j2`（auto_init 时创建，不覆盖）
- `data/templates/presets/distillation.j2`（auto_init 时创建，不覆盖）

**禁止修改**：
- `public/` 下任何契约文件（schema / interface_stub / config_template / pre_generated_mock / global_mock / test_cases / dependencies）
- 其他模块目录（`modules/模块3_*` / `modules/模块5_*` / `modules/模块6_*` 等）
- `backend/` 下任何文件
- `tests/spike_jinja2.py`（Spike 验证脚本，仅回归执行不修改）

### 3.2 依赖契约

- **接口契约**：`public/interface_stub/template_engine.pyi`（签名必须严格匹配）
- **数据契约**：`public/schema/template_registry.schema.json`（返回值必须通过校验）
- **配置契约**：`public/config_template/radix_config.json` 的 `template_engine` 段：
  - `templates_dir`（默认 `data/templates`）
  - `presets_dir`（默认 `data/templates/presets`）
  - `custom_dir`（默认 `data/templates/custom`）
  - `autoescape`（默认 `false`）
  - `trim_blocks`（默认 `true`）
  - `lstrip_blocks`（默认 `true`）

### 3.3 依赖的 Mock 路径

- `public/pre_generated_mock/mock_template_engine.py` — MockTemplateEngine Mock 实现
- **切换路径**：真实实现就位后，调用方只需修改导入路径：
  - Mock: `from public.pre_generated_mock.mock_template_engine import MockTemplateEngine as TemplateEngine`
  - 真实: `from modules.模块7_模板引擎 import TemplateEngine`
- 本模块**不依赖**其他模块的真实实现（模块3/5/6 并行开发中，尚未实现）。
- 如需依赖其他模块，使用 `public/pre_generated_mock/` 下的 Mock。

### 3.4 测试要求

- **Spike 回归**：`cd c:\CXHMS && python tests/spike_jinja2.py` 必须 5/5 PASS。
- **契约测试无回归**：`cd c:\CXHMS && python -m pytest tests/contract/radix_contract_test.py -v` 必须 105 passed。
- **实例化测试**：覆盖以下场景：
  - `render_template` 返回 `RenderResult` 含 3 字段（rendered_prompt / workflow_definition / expected_turns）
  - `list_templates` 返回非空列表（auto_init 后至少有 default + distillation 两个 preset）
  - `get_template` 返回 `TemplateRecord`
  - `create_template` + `delete_template` CRUD 闭环
  - 异常路径：`render_template` 缺 required_vars raise ValueError；`delete_template` 对 preset raise PermissionError；`get_template` 不存在 raise KeyError

### 3.5 错误码与异常契约（与 template_registry.schema.json definitions.exceptions 一致）

| 异常类型 | 触发方法 | HTTP 码 | 触发条件 |
|---------|---------|--------|---------|
| KeyError | get_template / render_template / update_template / delete_template | 404 | template_id 不存在 |
| ValueError | create_template / render_template / _parse_frontmatter | 422 | frontmatter 无效 / 缺 required_vars / workflow_mode 无效 / template_id 格式不合法 |
| PermissionError | update_template / delete_template | 403 | 尝试更新/删除 preset 模板 |
| FileExistsError | create_template | 409 | template_id 已存在 |
| jinja2.TemplateSyntaxError | render_template | 422 | Jinja2 语法错误 |
| jinja2.TemplateNotFound | render_template | 422 | extends 引用的父模板不存在 |
| IOError / OSError | create_template / update_template / delete_template | 500 | 文件 IO 异常 |
| RuntimeError | list_templates | 500 | 目录扫描异常 |

### 3.6 Jinja2 Environment 配置

- `Loader`: `ChoiceLoader([FileSystemLoader(presets_dir), FileSystemLoader(custom_dir)])`
- `autoescape`: `False`（模板是 prompt，不是 HTML）
- `trim_blocks`: `True`（去除块标签后的第一个换行）
- `lstrip_blocks`: `True`（去除块标签前的空白）
- 自定义 filter: `confidence_label`（0-1 → "低"/"中"/"高"）

### 3.7 排序规则（rules-0 §三 sorting.order: ascending）

- `list_templates` 按 `template_id` 升序排序。
- 目录扫描时 entries 按 `os.listdir` + `sorted` 排序。

---

## 四、参考

- 全局规则：`c:\CXHMS\AGENTS.md`
- AC 范式规则：`.trae/rules/rules-0..6.md`
- 接口契约：`public/interface_stub/template_engine.pyi`
- 数据契约：`public/schema/template_registry.schema.json`
- 配置契约：`public/config_template/radix_config.json`
- Mock 实现：`public/pre_generated_mock/mock_template_engine.py`
- Spike 验证：`tests/spike_jinja2.py`
- 契约测试：`tests/contract/radix_contract_test.py`
- 项目结构：`docs/ARCHITECTURE.md`、`docs/MODULES.md`
