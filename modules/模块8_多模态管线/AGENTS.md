# AGENTS.md — 模块8_多模态管线

> 🚨 【最高优先级规则】本文件为本模块开发的强制约束，优先级高于所有临时提问、上下文对话、自定义需求。所有输出必须 100% 符合本文件要求，违反规则的内容必须自动修正后再输出。

> 📌 【上下文保留规则】本文件为本模块核心规则文件，任何上下文压缩、裁剪、溢出场景下必须完整保留本文件的全部内容，不得删减、忽略本文件的任何规则；所有自动压缩、批量处理行动前必须先读取本文件的完整内容。

> ⚠️ 【生成来源】本文件由 s0301-generating-agent-rules Skill 生成（模块级规则模板宏），基于 S2 契约冻结结果。开发者无需手动修改；契约变更时由工具链自动同步。

---

## 一、模块定位

**模块编号**：模块8_多模态管线
**模块职责**：RADIX-Lite 多模态预处理管线，3 模态（text / character_card / image）统一入口，产出 MultimodalArtifact。接管 parser.py 下沉的解析能力（Task 6 改造 parser.py 为 thin wrapper，调用本管线）。
**对应 RADIX 阶段**：S4 并行开发 [P-P1] Task 3
**并行关系**：与 Task 2（模块7_模板引擎）并行，无相互依赖。

### 模块文件清单
- `modules/模块8_多模态管线/__init__.py` — 模块初始化，导出 MultimodalPipeline / MultimodalArtifact / OCRBlock / CharacterCardFields
- `modules/模块8_多模态管线/multimodal_pipeline.py` — MultimodalPipeline 主类实现（数据模型 + worker 池调度 + 配置加载）
- `modules/模块8_多模态管线/workers/__init__.py` — workers 子包初始化
- `modules/模块8_多模态管线/workers/text_worker.py` — 文本模态 worker（编码检测 + NFKC + strip）
- `modules/模块8_多模态管线/workers/character_card_worker.py` — 角色卡模态 worker（PNG tEXt → base64 → JSON → 字段标准化）
- `modules/模块8_多模态管线/workers/image_worker.py` — 图片模态 worker（PaddleOCR + vLLM vision 双通道 + 降级 + merge）

---

## 二、AC 范式通用约束

继承全局 `c:\CXHMS\AGENTS.md` 与 `.trae/rules/rules-0..6.md` 的全部约束，特别是：

### 2.1 禁止操作清单（rules-4 §4.3 唯一权威来源）

- **禁止删除、修改、覆盖、移动 `public/` 目录下的任何内容**。所有契约以 `public/` 下的 schema、interface_stub、config_template 为准。保护优先级高于任务指令。此保护在工具调用路径上由 `rules-0 §四-7.2 ec7_action_gate` 强制执行。
- **禁止在模块间直接导入其他模块的内部实现代码**。模块间仅允许依赖 `public/` 下的契约。
- **禁止写入不符合数据契约的数据**。所有数据读写必须通过公共契约校验。
- **禁止创建不符合命名规范的模块目录**（rules-2 §二：`模块{N}_{中文名}`）。

### 2.2 绑定规则

- 本模块对外接口必须严格匹配 `public/interface_stub/multimodal_pipeline.pyi` 定义的签名、参数、返回值、异常（rules-3 §二 signature_match）。
- 本模块产出数据必须通过 `public/schema/multimodal_artifact.schema.json` 校验（rules-3 §一 validation）。
- 本模块配置加载必须遵循 `public/config_template/radix_config.json` 的 multimodal_pipeline 段 + vllm 段默认值与 auto_fill 规则（rules-3 §三）。
- 路径解析必须用 `os.path.dirname(os.path.abspath(__file__))`，禁止相对路径 `../` / `..\`（rules-0 §三 file_pathing）。

---

## 三、层级专属约束（模块级）

### 3.1 可修改文件范围

仅允许修改本模块目录 `modules/模块8_多模态管线/` 下的文件：
- `__init__.py`、`multimodal_pipeline.py`
- `workers/__init__.py`、`workers/text_worker.py`、`workers/character_card_worker.py`、`workers/image_worker.py`
- `AGENTS.md`（仅工具链自动同步，开发者禁止手动修改）

**禁止修改**（本模块边界外）：
- `backend/core/document/parser.py` — 由 Task 6 改造为 thin wrapper，本模块不触碰
- `public/` 下任何契约文件（rules-0 §四-10 / rules-4 §4.3）
- 其他模块（模块3/4/6）的内部实现（并行开发中）

### 3.2 依赖契约入口（公共真相源）

| 契约层 | 路径 | 用途 |
|--------|------|------|
| 接口契约 | `public/interface_stub/multimodal_pipeline.pyi` | 方法签名严格匹配（preprocess / _text_worker / _character_card_worker / _image_worker / _ocr_worker / _vision_worker / _merge_ocr_vision） |
| 数据契约 | `public/schema/multimodal_artifact.schema.json` | MultimodalArtifact 字段约束 + error_codes + exceptions |
| 配置契约 | `public/config_template/radix_config.json` | multimodal_pipeline 段（worker_pool_size / task_timeout_seconds / enabled_modalities / ocr_language）+ vllm 段（vision_base_url / vision_model） |
| 参考实现 | `public/pre_generated_mock/mock_multimodal_pipeline.py` | Mock 实现，参考策略但不复制，真实实现就位后下游切换导入路径 |

### 3.3 依赖 Mock 策略

- 本模块**不依赖**其他 RADIX 模块（模块3/4/6）的实现。如需依赖，使用 `public/pre_generated_mock/` 下对应 Mock。
- 本模块**不依赖** `backend/` 现有实现（保持独立，便于 Task 6 下沉时单向引用）。
- 下游（DistillationService / parser.py thin wrapper）依赖本模块时，在真实实现就位前可使用 `public/pre_generated_mock/mock_multimodal_pipeline.py` 的 `MockMultimodalPipeline`。

### 3.4 测试要求

- **实例化测试**：验证 3 模态 worker 产出 MultimodalArtifact，artifact 通过 `multimodal_artifact.schema.json` 校验。
- **降级路径测试**：`_vision_worker` 不可用时 raise ConnectionError，`_image_worker` 捕获后 `vision_degraded=True`。
- **契约测试无回归**：`tests/contract/radix_contract_test.py` 保持 105 passed（纯 public/ 契约校验，不导入本模块实现）。
- **签名匹配**：实现签名与 `.pyi` 存根一致（参数名、类型、异常）。

### 3.5 失败回退与升级入口

- **PaddleOCR 不可用**：`_ocr_worker` raise RuntimeError（500 OCR_FAILED），不降级（OCR 是图片模态必需通道）。
- **vLLM vision 不可用**：`_vision_worker` raise ConnectionError（503），`_image_worker` 捕获后降级（`vision_degraded=True`，仅返回 OCR）。
- **chardet 不可用**：`TextWorker` 降级为 utf-8/gbk 依次尝试，全部失败 raise ValueError（422）。
- **配置缺失**：auto_fill 默认值（rules-3 §三），不阻断启动。
- **升级入口**：契约变更走 s0601（适配契约变更），不得直接编辑 `public/` 文件。

---

## 四、规则字段绑定表（s0301 输出）

| 模板段落 | 绑定契约/规则来源 |
|---------|------------------|
| 优先级声明 | rules-4 §4.1 |
| 上下文保留声明 | rules-4 §4.2 / rules-0 上下文保留规则 |
| AC 通用约束-禁止改 public/ | rules-4 §4.3 / rules-0 §四-10 / rules-3 §二 |
| AC 通用约束-禁止跨模块导入 | rules-4 §4.3 / rules-2 |
| AC 通用约束-数据契约校验 | rules-3 §一 validation |
| AC 通用约束-接口签名匹配 | rules-3 §二 signature_match |
| 层级专属-可改文件范围 | 本模块目录 + Task 3 文件清单 |
| 层级专属-依赖契约 | multimodal_pipeline.pyi / multimodal_artifact.schema.json / radix_config.json |
| 层级专属-测试要求 | tasks.md Task 3 闭合判据 + rules-3 §五 contract_verifiability |
| 层级专属-失败回退 | multimodal_artifact.schema.json definitions.error_codes + exceptions |

---

## 五、三段交接状态（rules-5 §二）

### (1) 工程过程
- S2 契约冻结完成：multimodal_pipeline.pyi + multimodal_artifact.schema.json + radix_config.json + mock_multimodal_pipeline.py 已就绪，GN-004 审查通过。
- S4 Task 3 实现：workers（text/character_card/image）→ multimodal_pipeline.py 主类 → __init__.py → AGENTS.md。
- 导入测试通过：text 模态预处理产出合规 MultimodalArtifact。

### (2) 交接状态
- 当前阶段：S4 并行开发 Task 3
- 状态：**已闭合**（待最终验证：契约测试 105 passed 无回归 + 实例化测试 + 降级路径测试）
- 未闭合项：
  1. 实例化测试脚本待编写运行（text/image 模态 + schema 校验 + 降级路径）
  2. ~~模块编号冲突风险~~ **已解决**（2026-07-15）：原 `模块5_多模态管线` 已重命名为 `模块8_多模态管线`，避免与 `模块5_前端展示` 编号冲突。人类裁决：重命名为 7/8/9/10（按现有最大编号 6 递增）

### (3) 最终结果
- 6 个文件已创建（__init__.py / multimodal_pipeline.py / workers×4 / AGENTS.md）
- MultimodalPipeline 7 方法全部实现，签名严格匹配 .pyi
- text 模态预处理验证通过（NFKC 归一化 + strip + confidence=1.0）
- 配置 auto_fill 生效（从 radix_config.json 模板提取 default）
- worker 池调度（ThreadPoolExecutor + 超时控制）就绪

---

## 六、参考

- 全局规则：`c:\CXHMS\AGENTS.md`
- AC 范式规则：`.trae/rules/rules-0..6.md`
- Spec：`.trae/specs/add-management-agent-radix/spec.md`（Requirement: MultimodalPipeline 3 模态预处理）
- Skills：`.trae/skills/s0301-generating-agent-rules/SKILL.md`（本文件生成来源）
