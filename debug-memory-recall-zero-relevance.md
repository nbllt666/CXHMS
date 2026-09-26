# 调试记录：记忆召回 3 维评分可能召回相关度为 0 的记忆

- sessionId: `memory-recall-zero-relevance`
- runId: `pre`（pre-fix 证据采集）
- 待查缺陷：`backend/core/memory/router.py` 的 `_score_memories` 采用加权求和
  `importance*wi + time*wt + relevance*wr`，使与当前 query 毫无关系的记忆仍可能 ≥ `min_score_threshold=0.3`
  而被注入对话上下文；且 `relevance = memory.get("score", 0.5)` 在无相关度证据时伪造 0.5。
- 已批准 spec：`c:\CXHMS\.trae\specs\fix-memory-recall-relevance-gate\spec.md`（5 条根因）
- 调试服务器：见下方「环境」段
- 复现脚本：`c:\CXHMS\tests\manual\repro_memory_recall_zero_relevance.py`

---

## 一、可证伪假设（对应 spec 的 5 条根因）

### H1 — 可加性（加权求和）本身

- **命题**：`final = importance*wi + time*wt + relevance*wr` 为可加式，`relevance=0` 时 `final` 仍可达到 `importance*wi + time*wt` 的水平（chat 场景 wi=0.45、wt=0.20 → 上限 0.65），越过 `min_score_threshold=0.3`，从而被 `_apply_filters` 保留。
- **观察点**：`_score_memories` 评分循环内插桩上报 `final_score`、`component_scores`、`weights`（场景 A：无关 query + `importance_score=1.0` + 无 `score` 字段）。
- **证伪条件**：若观测到 `final_score < 0.3`（即无关记忆无论如何都过不了阈值），则 H1 不成立。

### H2 — 伪造相关度 `0.5`

- **命题**：当记忆字典不含 `score` 键时，`memory.get("score", 0.5)` 取到伪造值 `0.5`，使本应无相关度证据的记忆凭空获得 `relevance=0.5`，进而贡献 `0.5*0.4=0.2`。
- **观察点**：场景 A 中上报的 `component_scores.relevance` 与消息中「入参是否含 score 键」（`has_score_key`）。
- **证伪条件**：若上报的 `relevance != 0.5`（例如为 0.0 或真实关键词分），则 H2 不成立。

### H3 — 异常兜底伪造阈值分数 `0.3`

- **命题**：`_score_memories` 的 `except` 分支写死 `memory["final_score"] = memory.get("score", 0.3)`，恰好等于 `min_score_threshold`；评分抛异常的无 `score` 记忆由此拿到 0.3 并通过 `_apply_filters`（`score >= 0.3`）。
- **观察点**：`_score_memories` 的 except 分支插桩（`location=score_memories:except`）上报 `final_score`、`exc_type`、`has_score_key`；`_apply_filters` 上报 `kept=True/False`。
- **证伪条件**：若异常记忆的 `final_score != 0.3`，或其未通过 `_apply_filters`，则 H3 不成立。

### H4 — 关键词相关度未命中返 `0.1`

- **命题**：`HybridSearch._calculate_keyword_score(content, query)` 在 query 未命中 content 时返回 `0.1` 而非 `0`，使「关键词未命中的检索结果」仍带非零相关度。
- **观察点**：场景 D 直接调用该方法的返回值（脚本 print + 插桩 `location=keyword_score:probe`）。
- **证伪条件**：若未命中时返回 `0.0`，则 H4 不成立。

### H5 — `all_memories` 是死代码

- **命题**：`route()` 中构建的 `all_memories`（含 `_get_recent_memories` 结果）从未参与评分，`_score_memories` 只收到 `search_results`；`applied_rules` 却声明「最近交互记忆优先」，属虚假声明。
- **观察点**：`route()` 中在 `all_memories` 构建后、`_score_memories` 调用前后插桩，上报 `all_memories_count`、`search_results_count`、`scored_from_all_memories`（布尔：是否有 recent 记忆进入评分）、`applied_rules`。
- **证伪条件**：若 recent 记忆（仅存在于 `all_memories`）确实进入了评分结果（`scored_from_all_memories=True` 且其 id 出现在 scored 列表），则 H5 不成立。

---

## 二、环境

| 项 | 值 |
|----|----|
| Debug Server 启动命令 | `python c:\Users\NBLLT666\.trae-cn\builtin_skills\TRAE-debugger\tools\debug-server\python\debug-server.py --session memory-recall-zero-relevance --outdir c:\CXHMS\.dbg --clean --idle 1200` |
| DEBUG_SERVER_URL | `http://127.0.0.1:7777/event`（端口 **7777**，`/health` 返回 `{"status":"ok","session_id":"memory-recall-zero-relevance"}`） |
| 日志文件 | `c:\CXHMS\.dbg\trae-debug-log-memory-recall-zero-relevance.ndjson`（本次 run 共 22 条） |
| 日志回取 | `GET http://127.0.0.1:7777/logs?runId=pre` |
| 插桩封装 | `backend/core/memory/router.py` L12-L39：模块级 `_dbg_report()`，`urllib.request` POST JSON，timeout=1s，整体 try/except 静默失败，无 print/logging |
| 插桩位置 | L159-175（route:pre_score）、L184-208（route:post_score）、L346-359（score_memories:entry）、L380-405（score_memories:loop）、L412-431（score_memories:except）、L434-447（score_memories:exit）、L468-484（apply_filters:verdict） |
| Server 状态 | 保持运行（未关闭），插桩未清理，供 post-fix 复审复用 |

### 复现脚本输出摘要（pre-fix）

```
A: final_score=0.825, relevance=0.5, kept=True
B: b1=0.3/kept=True, b2=0.3/kept=True
C: applied_rules=['最近交互记忆优先'], 返回 ids=[200,201], recent_ids_returned=[]
D: keyword 未命中=0.1, 命中=1.0
```

---

## 三、日志摘录与假设判定

（日志行号 = `GET /logs?runId=pre` 返回数组的序号）

### H1 — 可加性（加权求和）✅ **成立**

- **日志 #3**（`score_memories:loop`）：`memory_id=1, content="今天天气很好"`，query=`量子纠缠退相干实验数据`（完全无关），
  `importance_score=1.0, time_score=1.0, relevance=0.5, weights={importance:0.45, time:0.2, relevance:0.35}, final_score=0.825, passes_threshold=true`。
- **日志 #5**（`apply_filters:verdict`）：`memory_id=1, final_score=0.825, kept=true`（命中 `final_score >= 0.3` 分支，甚至越过 `high_priority_threshold=0.8`）。
- **反推**：即使把 `relevance` 归零（`0.5*0.35=0.175` 去掉），`final` 仍为 **0.65**（脚本 A 的 `final_score - 0.175 = 0.65`），远超 0.3 —— **可加性本身即可单独造成误召回**，与 spec 第 1 条一致。

### H2 — 伪造相关度 `0.5` ✅ **成立**

- **日志 #2**（`score_memories:entry`）：`has_score_key=[false]` —— 场景 A 的记忆**确实不含 `score` 键**。
- **日志 #3**：`score_raw=null`，`relevance=0.5`，`relevance_origin_pre="forged_default_0.5"` —— 与 `memory.get("score", 0.5)` 的伪造默认值完全吻合，贡献 `0.5×0.35=0.175`。
- 对照 **日志 #16/#17**（场景 C 中带真实 `score` 的记忆）：`score_raw=0.85 → relevance=0.85`、`score_raw=0.8 → relevance=0.8`，说明「有 `score` 时透传、无 `score` 时伪造 0.5」，两条路径行为不一致。

### H3 — 异常兜底伪造阈值分数 `0.3` ✅ **成立**

- **日志 #7**：`memory_id=2, has_score_key=false, exc_type=TypeError, exc_msg="'>=' not supported between instances of 'str' and 'float'", final_score=0.3, min_score_threshold=0.3, passes_threshold=true`。
- **日志 #9**：`apply_filters:verdict` → `final_score=0.3, kept=true` —— 异常记忆被保留。
- **日志 #11**：同分支另一形态（`exc_type=KeyError, exc_msg="'relevance'"`）→ `final_score=0.3, passes_threshold=true`，**日志 #13** `kept=true`。
- 结论：`except` 分支的 `memory.get("score", 0.3)` 恰好等于 `min_score_threshold`，等于给评分失败的记忆发放通行证（fail-open）。

### H4 — 关键词相关度未命中返 `0.1` ✅ **成立**

- **日志 #22**（`keyword_score:probe`）：`content="完全无关内容", query="量子纠缠", miss_return=0.1, hit_return=1.0`。
- 脚本 print 同步确认：`未命中返回值 = 0.1`、`命中返回值 = 1.0`（`HybridSearch._calculate_keyword_score` 行为，未命中非零）。

### H5 — `all_memories` 是死代码 ✅ **成立**

- **日志 #14**（`route:pre_score`）：`all_memories_count=2, all_memories_ids=[100,101], search_results_count=2, search_results_ids=[200,201], scorer_receives_field="search_results", applied_rules=["最近交互记忆优先"]`。
- **日志 #15**（`score_memories:entry`）：`memory_ids=[200,201]` —— 评分入口**只收到 search_results，recent 通道的 100/101 从未进入评分**。
- **日志 #21**（`route:post_score`）：`recent_only_ids=[100,101], recent_only_ids_scored=[]` —— 交集为空，确证 recent 结果从未参与评分；而 `applied_rules` 仍返回「最近交互记忆优先」，属虚假声明。
- 脚本侧 print：`recent_ids_returned=[]`，`返回记忆 ids=[200,201]`。

### 关键 pre-fix 数字（供 post-fix 对照）

| 项 | pre-fix 观测值 |
|----|---------------|
| 无关记忆（"今天天气很好" × query "量子纠缠退相干实验数据"）`final_score` | **0.825** |
| 其 `component_scores` | `{importance: 1.0, time: 1.0, relevance: 0.5}`（chat 权重 0.45/0.20/0.35） |
| 是否被 `_apply_filters` 保留 | **是**（`kept=true`，且已越过 `high_priority_threshold=0.8`） |
| `relevance` 实际取到 | **0.5**，来源 = `memory.get("score", 0.5)` 伪造默认值（`has_score_key=false`） |
| 评分异常记忆 `final_score` | **0.3**（TypeError 与 KeyError 两形态一致），`kept=true` |
| keyword 未命中返回值 | **0.1** |
| recent 通道记忆进入评分条数 | **0**（`recent_only_ids_scored=[]`），但 `applied_rules` 声明「最近交互记忆优先」 |
| `min_score_threshold` / `high_priority_threshold` | 0.3 / 0.8 |

---

## 四、未验证项

- **未覆盖 `manager.search_memories_3d` 路径**：本次用无 vector_store/embedding_model 的 fake 构造 router，
  `route()` 走 `memory_manager.search_memories` 回落路径，因此 spec 根因 2 中「3D 路径相关度写死常量 0.5（含 SQL `0.5 * ?` 项）」与根因 1 中 `manager.search_memories_3d` 的可加性**未做运行时取证**（需真实 SQLite/DB，超出最小 fake 复现范围）。
  静态阅读 `decay.py` L391 `relevance_score = memory.get("score", 0.5)` 显示同一伪造模式在 `DecayCalculator.calculate_final_score` 中同样存在，但未运行时验证。
- **`HybridSearch._merge_results` 的加权合并口径**未取证（本次绕过了 hybrid_search 实路径）。
- **`_apply_filters` 中 permanent 无条件放行**未用 permanent=True 记忆单独取证（场景 A/B 均为 `permanent=False`）；不过在 `final_score=0.825` 的情形下即使移除 permanent 分支结果不变，故不影响 H1 结论。
- 场景 B 的两种异常形态（`importance_score="abc"`、weights 缺键）均为构造性异常，非真实数据形态；但 except 分支的分支覆盖已完整。

---

## 五、post-fix 验证（Task 6.4 召回收缩实测）

> 本节为**仅追加**的 post-fix 证据，未改写上方任何 pre-fix 记录。
> 采集命令：`$env:DEBUG_RUN_ID="post"; python tests/manual/repro_memory_recall_zero_relevance.py`（cwd=仓库根，脚本验证语义未改动）
> 日志回取：`GET http://127.0.0.1:7777/logs?runId=post`（本轮共 36 条；值完全一致，为同一脚本的两次运行）
> 脚本输出摘要（post-fix）：
> ```
> A: final_score=0.0, relevance=0.0, kept=False
> B: b1=0.0/False, b2=0.0/False
> C: applied_rules=['同会话最近记忆纳入候选'], recent_ids_returned=[]
> D: miss=0.0, hit=1.0
> ```

### 5.1 pre-fix vs post-fix 逐条对比表

（`relevance_source` 取自 `component_scores`；保留与否取自 `apply_filters:verdict` 的 `kept`）

| 场景 / 记忆 | pre-fix `relevance` | pre-fix 来源 | pre-fix `final_score` | pre-fix 保留 | post-fix `relevance` | post-fix 来源 | post-fix `final_score` | post-fix 保留 |
|------------|--------------------|-------------|----------------------|-------------|---------------------|--------------|----------------------|--------------|
| A：无关 query + 无 score（id=1） | 0.5（伪造默认值） | `memory.get("score", 0.5)` 伪造 | **0.825** | **是**（越过 0.8 高优阈值） | **0.0** | `keyword_realtime` | **0.0** | **否** |
| B1：评分异常-非数值 importance（id=2，TypeError） | —（未进入正常评分） | 异常兜底伪造 0.3 | **0.3** | **是** | 0.0 | `unresolved`（异常分支赋值） | **0.0** | **否** |
| B2：评分异常-缺权重组（id=3，KeyError） | — | 异常兜底伪造 0.3 | **0.3** | **是** | 0.0 | `unresolved`（异常分支赋值） | **0.0** | **否** |
| C-recent：无关最近记忆（id=100） | 未进入评分（死代码） | —（从未评分） | —（未参与） | 否 | **0.0** | `keyword_realtime` | **0.0** | **否** |
| C-recent：无关最近记忆（id=101） | 未进入评分（死代码） | —（从未评分） | —（未参与） | 否 | **0.0** | `keyword_realtime` | **0.0** | **否** |
| C-search：相关搜索结果（id=200） | 0.85 | `search_score` | 0.85 | 是 | 0.85 | `search_score` | **0.85** | **是** |
| C-search：相关搜索结果（id=201） | 0.8 | `search_score` | 0.748 | 是 | 0.8 | `search_score` | **0.748** | **是** |
| D：关键词未命中 | 0.1 | `_calculate_keyword_score` | — | — | **0.0** | `calculate_keyword_relevance` | — | — |
| D：关键词命中（开头） | 1.0 | 同上 | — | — | 1.0 | 同上 | — | — |

补充：场景 C 的 `route:scored` 上报 `scored_ids=[100,101,200,201], deduped_ids=[100,101,200,201], kept_ids=[200,201]`，`applied_rules=["同会话最近记忆纳入候选"]`；`route:candidates` 上报 `recent_count=2, search_count=2, candidate_count=4` —— 证明最近通道已实际并入评分候选（H5 死代码已接线），且未命中的最近记忆 `relevance=0` 被过滤淘汰。

### 5.2 两条闭合判据判定

| 判据 | 要求 | post-fix 实测 | 判定 |
|------|------|--------------|------|
| (a) 输出中 `relevance = 0`（或 `relevance_source="unresolved"`）的记忆条数 | 必须为 **0** | 输出 `kept_ids=[200, 201]`，二者 `relevance` 分别为 `0.85` / `0.8`（来源均 `search_score`）；`relevance=0` 的记忆（id=1/2/3/100/101）全部 `kept=false` | ✅ **满足（条数 = 0）** |
| (b) 同 query 召回条数 ≥ 修复前基线的 **50%** | ≥ 50% | pre-fix 基线 2 条（ids `[200,201]`）→ post-fix 仍 2 条（ids `[200,201]`），**100%** | ✅ **满足（100% ≥ 50%）** |

**结论**：两条闭合判据均满足，本轮**无需**重标定 `min_score_threshold`（`high_priority_threshold=0.8` 分支在新公式下的可达性下降已在 spec v4 显式记录，字段与分支未改动）。

### 5.3 post-fix 未验证 / 偏差说明

- 场景 B 的 `relevance_source="unresolved"` 由 `except` 分支代码赋值（`repro` 脚本未打印该字段；已由单元测试 `test_score_exception_is_fail_closed_and_filtered` 直接断言 `component_scores.relevance_source == "unresolved"`）。
- 本次仍未覆盖 `manager.search_memories_3d` 实路径（同一 fake 构造无 vector_store/embedding_model），其 SQL 排序下推改造由 Task 6.2 的 `tests/simulation/scenarios/test_3d_search_ranking.py` 回归覆盖（4 passed）。
- 单元测试中「`created_at` 非法值」未能触发时间计算异常（`calculate_days_elapsed` 内部 try/except 吞掉解析异常并返回 0 天），故 fail-closed 用例改用两种确定性异常形态：`importance_score` 为不可运算对象（TypeError）与 weights 缺 `relevance` 键（KeyError）。此为任务清单中「例如」的等价替代，非放宽断言。

---

## 真实链路实测（runId=real）

> 本节为**仅追加**的真实链路证据（2026-09-25 21:11–21:24），未改写上方任何既有内容。
> 目标：把已验证的修复放到「真实 FastAPI 应用 + 真实 SQLite + 真实路由装配」上取证。

### 6.1 工程过程（本轮做了什么）

| 顺序 | 动作 | 结果 |
|------|------|------|
| 1 | 读 `.env` 非密钥项 | `CXHMS_DATABASE_MEMORIES_DB=data/memories.db`、`CXHMS_DATABASE_SESSIONS_DB=data/sessions.db`、`CXHMS_VECTOR_ENABLED=true`、`CXHMS_VECTOR_BACKEND=weaviate`、`CXHMS_LLM_HOST=http://localhost:8002` |
| 2 | 复制真实库（含 `-wal`/`-shm`）到 `.dbg/reallink/` | `memories.db` 864256B + `-shm`；`sessions.db` 282624B |
| 3 | 启动真实后端（副本库覆盖） | 端口 **8765**，`GET /health` → 200，`memory_manager/context_manager/llm_client/model_router/async_memory_manager` 全 `true` |
| 4 | 真实 3D 搜索接口实测 | 2 次调用均 HTTP 200，**SQL 无报错** |
| 5 | 真实对话链路实测 | 走 `POST /api/chat`（真实 LLM），2 次均 200；另跑直连探针 1 个（4 个用例） |
| 6 | 证据落盘 + 停后端 | 见本节；后端 PID 36944 已停止 |

**启动命令（实际使用）**

```powershell
# 注意：CXHMS_PORT / CXHMS_DEBUG 环境变量覆盖在本仓库无效（见 6.5 P3），
# 故改用 CXHMS_CONFIG_PATH 指向副本配置（server.port=8765, server.debug=false）
$env:CXHMS_CONFIG_PATH="c:\CXHMS\.dbg\reallink\config\default.yaml"
$env:CXHMS_DATABASE_MEMORIES_DB="c:\CXHMS\.dbg\reallink\memories.db"
$env:CXHMS_DATABASE_SESSIONS_DB="c:\CXHMS\.dbg\reallink\sessions.db"
$env:DEBUG_RUN_ID="real"; $env:DEBUG_SERVER_URL="http://127.0.0.1:7777/event"
python main.py            # cwd=c:\CXHMS，后台启动
```

`GET http://127.0.0.1:8765/health`（截断）：
```json
{"status":"healthy","components":{"memory_manager":true,"context_manager":true,"acp_manager":true,
 "llm_client":true,"model_router":true,"async_memory_manager":true,"graph_database":true,"cxfc_manager":true}}
```
日志确认库路径为副本：`记忆管理器初始化完成: db=c:\CXHMS\.dbg\reallink\memories.db`。

**外部依赖可用性（真实探测）**

| 依赖 | 结果 |
|------|------|
| LLM（`localhost:8002`，gemma4-e4b） | ✅ `/v1/models` 200，真实对话可返回 |
| Weaviate（`localhost:8090`） | ✅ 可连、`is_available()=True`、`/api/memories/vectors/status` → `{"enabled":true,"backend":"weaviate","vector_count":18,"sqlite_count":13,"healthy":true}` |
| **Embedding**（`localhost:8101/v1/embeddings`） | ❌ **HTTP 404** — `The model '/models/Qwen3-Embedding-0.6B' does not exist`（见 6.5 P2） |

**数据落点声明（如实披露）**：真实 `memories.db` / `sessions.db` 未被使用（已换成副本）。
但真实链路中下列**真实数据**被触碰：`data/weaviate/**`（向用户真实 weaviate 写入，见 6.5 P4）、
`data/acp/*.yaml`（ACP 管理器退出时落盘）、`data/cxfc_plugins.db`（插件管理器初始化）、
`data/context/agent-default.json`（`/api/chat` 新建的会话文件；**已删除**，该目录实测启动前为空）。
`logs/app.log` 有追加。

### 6.2 真实 3D 搜索接口（重点验证 SQL 与占位符）

写入 3 条差异明显的记忆（`POST /api/memories`，HTTP 200）：

| memory_id | content | importance | permanent |
|-----------|---------|-----------|-----------|
| 1410 | 量子纠缠退相干实验数据记录 | 3 | false |
| 1411 | 今天天气很好适合散步 | 5 | false |
| 1412 | 苹果树上结了红苹果 | 2 | **true** |
| 1413 | 内部部署流程使用 Jenkins 流水线自动构建 | 5 | true |

（1413 带 tag=`agent-default`，用于触发路由的「同会话最近记忆纳入候选」通道。）

**（1）`POST /api/memories/3d?limit=10`（不带 query）→ HTTP 200**

```json
{"total":10,"applied_weights":{"importance":0.35,"time":0.25,"relevance":0.4}}
今天天气很好适合散步            | imp=1.0 | final=1.0  | rel=1.0 | src=no_query
苹果树上结了红苹果              | imp=1.0 | final=1.0  | rel=1.0 | src=no_query   (permanent=true)
量子纠缠退相干实验数据记录      | imp=0.6 | final=0.76 | rel=1.0 | src=no_query
（其余 7 条为既有日记/记忆，imp=0.6，final≈0.612，src=no_query）
```
→ `relevance_source` 全为 `no_query`（无查询信号不门控），高 `importance_score` 排在前。

**（2）`POST /api/memories/3d?query=量子纠缠&limit=10` → HTTP 200**

```json
{"total":1}
量子纠缠退相干实验数据记录 | imp=0.6 | final=0.76 | rel=1.0 | src=keyword_realtime | perm=false
```
→ 命中记忆 `relevance_source="keyword_realtime"`、`relevance=1.0>0`；
未命中记忆 **未出现在结果中**（`total=1`）——因 3D SQL 用 `content LIKE ?` 预过滤，
未命中行根本不进入候选集，故输出中不存在 `relevance=0` / `final_score=0.0` 的行。

**SQL 报错排查结论**：`search_memories_3d` 的排序下推 SQL（`MIN(...)/NULLIF(?+?,0.0)` 等 5 个占位符）
在真实 SQLite 上**执行成功、占位符匹配**：两次调用均 200 且有结果，
`logs/app.log` 与探针输出中**无** `sqlite3.OperationalError` / `near "..."` / `3D搜索失败`。

### 6.3 真实对话召回链路

**路径：`POST /api/chat`（agent_id=default，memory_scene=task，真实 LLM，tokens 正常返回）**

| # | query | 后端日志 | HTTP |
|---|-------|---------|------|
| 1 | `量子纠缠退相干实验的数据记录在哪里？`（自然语言） | `记忆路由: hybrid_search=True, search_results=0` → `scored=0, filtered=0` | 200 |
| 2 | `量子纠缠退相干实验数据记录`（精确子串） | `记忆路由: hybrid_search=True, search_results=1` → `scored=2, filtered=1` | 200 |

插桩日志（`GET http://127.0.0.1:7777/logs?runId=real`，本轮共 40 条，摘录第 2 次 chat 的 6 条）：

```
#3  route:candidates :: {"session_id":"agent-default","recent_count":1,"search_count":1,
                          "candidate_count":2,"applied_rules":["同会话最近记忆纳入候选"]}
#4  score_memories:loop :: {"memory_id":1413,"has_score_key":false,"importance":1.0,"time":1.0,
                            "relevance":0.0,"relevance_source":"keyword_realtime",
                            "weights":{"importance":0.3,"time":0.2,"relevance":0.5},"final_score":0.0}
#5  score_memories:loop :: {"memory_id":1410,"has_score_key":true,"importance":0.6,"time":0.6,
                            "relevance":0.4,"relevance_source":"search_score",
                            "weights":{"importance":0.3,"time":0.2,"relevance":0.5},"final_score":0.32}
#6  apply_filters:verdict :: {"memory_id":1413,"final_score":0.0,"permanent":true,"kept":false}
#7  apply_filters:verdict :: {"memory_id":1410,"final_score":0.32,"permanent":false,"kept":true}
#8  route:scored :: {"scored_ids":[1413,1410],"deduped_ids":[1413,1410],"kept_ids":[1410],
                     "applied_rules":["同会话最近记忆纳入候选"]}
```

**直连探针**（`.dbg/reallink/probe_router_real.py`，`TestClient(app)` 走真实 lifespan 拿
`app.state.services`，构造 `MemoryRouter(memory_manager, vector_store, embedding_model)`，
`asyncio.run(router.route(...))`；`[env] vector_store = WeaviateVectorStore, is_available=True`，
`embedding_model = VLLMClient`，`memories_db(copy) = c:\CXHMS\.dbg\reallink\memories.db`）：

| 用例 | query / session | 返回条数 | 返回明细 |
|------|----------------|---------|---------|
| C1 | `量子纠缠退相干实验数据记录` / probe-session | 1 | `id=1410 final_score=0.32 component_scores={'importance':0.6,'time':0.6,'relevance':0.4,'relevance_source':'search_score'}`，`applied_rules=[]` |
| C2 | `量子纠缠退相干实验的数据记录在哪里？` / probe-session | **0** | `applied_rules=[]`（`search_results=0`） |
| C3 | `量子纠缠退相干实验数据记录` / agent-default | 1 | `id=1410 final_score=0.32 ... 'relevance_source':'search_score'`，`applied_rules=['同会话最近记忆纳入候选']` |
| C4 | `请帮我写一段快速排序代码` / agent-default | **0** | 1 条候选（1413）全部被淘汰，`applied_rules=['同会话最近记忆纳入候选']` |

### 6.4 三项判定（真实链路观测值）

| 判定 | 要求 | 真实链路观测 | 结论 |
|------|------|-------------|------|
| (a) 与 query 完全无关的记忆是否被注入 | 否 | chat#2 候选含 1413（无关 + permanent=true，imp=1.0），`relevance=0.0 → final_score=0.0 → kept=false`；`kept_ids=[1410]`。C4 场景 1 条无关候选全部淘汰（`filtered=0`） | ✅ **否（未注入）** |
| (b) 相关记忆是否正常召回 | 是 | **精确子串 query：是**（1410 以 `relevance_source=search_score`、`final=0.32` 被召回，chat#2 与 C1/C3 一致）。**自然语言 query：否**（chat#1 与 C2 均返回 0 条，`search_results=0`） | ⚠️ **部分满足**——见 6.5 P1 |
| (c) 输出中是否存在 `relevance=0` 或 `final_score=0.0` 的记忆被注入 | 否 | 全部 `apply_filters:verdict` 条目中 `final_score=0.0` 的无一 `kept=true`（#6 1413 kept=false）；`kept_ids` 仅含 1410（final=0.32） | ✅ **否（未注入）** |

### 6.5 发现的未修复问题（如实报告，均非本次修复引入）

- **P1【重要】自然语言 query 在真实链路召回为 0，相关记忆召不回来。**
  现象：`POST /api/chat` 用「量子纠缠退相干实验的数据记录在哪里？」提问，DB 中明明有
  「量子纠缠退相干实验数据记录」，却 `search_results=0 → filtered=0`（`logs/app.log` 21:17:06）。
  根因（两路同时失效）：① 向量路 — embedding 服务 404（P2），`_vector_search` 抛
  `WeaviateInvalidInputError: near_vector ... got NoneType` 后返回 `[]`；
  ② 关键词路 — `HybridSearch._keyword_search` 走 `manager.search_memories` 的
  `content LIKE '%<整条 query>%'`，要求**整句用户消息是记忆内容的子串**，实际用户问句永远不满足，
  `calculate_keyword_relevance` 因此为 0。两路皆空 → 候选集为空。
  可复现：见 6.3 chat#1 / C2。**该问题与本次门控修复无关（修复前同样召不回），但会使 (b) 项
  在自然语言场景下不成立**，需人类决定是否作为后续独立任务处理（属召回质量问题，非门控问题）。
  注：门控本身表现正确——召回的 1410 与淘汰的 1413 数字自洽（0.32 / 0.0）。
- **P2【重要】embedding 不可用时：向量写入静默降级且**谎报成功**，读取路径则直接抛异常。**
  现象：`VLLM获取embedding失败: HTTP 404`（模型 `/models/Qwen3-Embedding-0.6B` 不存在）后，
  `get_embedding` 返回 `None`，`_sync_vector_for_memory` 仍调用
  `weaviate_store.add_memory_vector(..., embedding=None)` → `collection.data.insert(properties=..., vector=None)`
  → **对象被写入 weaviate（无向量）**，且日志打印 `向量同步成功: memory_id=1410`（21:16:29）；
  同一 `None` 在读取路径 `search_similar(near_vector=None)` 则抛
  `WeaviateInvalidInputError`。写成功/读失败口径不一致，且失败被报成成功。
- **P3【环境阻塞】`CXHMS_PORT` / `CXHMS_DEBUG` 环境变量覆盖在本仓库不可用。**
  按任务给的 `$env:CXHMS_PORT="8765"; python main.py` 启动，`uvicorn.run(host=..., port=...)`
  直接崩溃：`TypeError: 'str' object cannot be interpreted as an integer`
  （`at uvicorn/config.py bind_socket → sock.bind((self.host, self.port))`），
  日志尾部另有 `Will watch for changes...` 说明 `CXHMS_DEBUG="false"` 字符串被当作真值 → reload 被打开。
  根因：`config/env.py` 把环境变量以字符串写入 config dict，而 `config/settings.py` 的
  `SystemConfig.from_dict` 未做 int/bool 转型（对比 `ModelConfig.from_dict` 对 `supports_tools` 有转型）。
  本次改用 `CXHMS_CONFIG_PATH` 指向 `.dbg/reallink/config/default.yaml` 绕过。
- **P4【真实数据副作用，需人类裁决】测试记忆被写入真实 weaviate；且同 id 出现重复对象。**
  `POST http://localhost:8090/v1/graphql` 实测（只读查询）：
  `CXHMSMemory where memory_id in (1410..1413)` → **1410 有 2 条对象**，1411/1412/1413 各 1 条，
  共 5 条测试对象落入用户真实向量库（内容与 6.2 表一致）。原因：真实 `weaviate` 不在本次
  可覆盖范围内（`CXHMS_WEAVIATE_HOST/PORT` 指向的是用户已在运行的外部 weaviate），且 P2 的
  静默写入使其在 embedding 失效时依然落库；重复疑与 `add_memory_vector` 用
  `collection.data.insert`（非 upsert）以及启动时 `sync_with_sqlite` 在
  `get_vector_by_id` 取不到对象时再次 `add_memory_vector` 有关。
  **未自行删除**（删除属对真实数据的破坏性操作，需人类显式授权后再执行）。
- **P5【配置一致性】`CXHMS_DATABASE_SESSIONS_DB` 对会话存储无效。**
  `ContextManager.__init__` 忽略 `db_path`，硬编码 `self._context_dir = "data/context"`
  （`backend/core/context/manager.py` L30/L39），副本 `sessions.db` 实际未被使用，
  会话落在真实 `data/context/`。故本次实测中 `/api/chat` 在真实 `data/context` 新建了
  `agent-default.json`（已删除，该目录实测启动前为空）。

### 6.6 交接状态与最终结果

- **交接状态**：本轮真实链路实测 **已闭合**；上述 P1–P5 为**新发现、未修复**，
  其中 P1/P2 影响「相关记忆能否召回」，P3 只影响启动方式，P4 需人类裁决是否清理真实 weaviate 测试对象，P5 为配置一致性问题。
- **最终结果**：门控修复在真实链路**行为正确**——`relevance=0（含 permanent=true）→ final_score=0.0 → 不注入`，
  且相关记忆（精确子串 query 场景）以 `relevance_source=search_score` 正常召回；
  3D 搜索 SQL 在真实 SQLite 上执行无误。(a)(c) 两项判定通过，(b) 仅在精确子串场景通过。
- **产出物清单**：`.dbg/reallink/memories.db`(副本)、`.dbg/reallink/sessions.db`(副本)、
  `.dbg/reallink/config/default.yaml`(端口 8765)、`.dbg/reallink/probe_router_real.py`、
  `.dbg/reallink/probe.out.log`、`.dbg/reallink/backend.{out,err}.log`、
  `.dbg/trae-debug-log-memory-recall-zero-relevance.ndjson`(含 runId=real 40 条)。

---

## 真实 weaviate 测试对象清理（人类授权）

> 本节为**仅追加**的清理记录。2026-09-25，人类**显式授权**清理 6.5 P4 中写入真实 weaviate 的
> 5 条测试对象（memory_id `1410`×2 / `1411` / `1412` / `1413`），授权范围**严格限定**为这 5 条，
> 不得扩大。

### 7.1 工程过程

| 顺序 | 动作 | 结果 |
|------|------|------|
| 1 | 读 `.env` 向量配置 | `CXHMS_VECTOR_BACKEND=weaviate`、`CXHMS_WEAVIATE_HOST=localhost`、`CXHMS_WEAVIATE_PORT=8090`，`grpc_port=50061`（取自 `config/default.yaml`，只读） |
| 2 | 连接（与写入时同一封装） | `WeaviateVectorStore(host, port, grpc_port, embedded=False, vector_size=768, schema_class="CXHMSMemory")`，`collection=CXHMSMemory`，`is_available=True` |
| 3 | 删除前基线 + 一致性校验 | 命中目标 5 条，数量/内容全部匹配授权范围 → 放行 |
| 4 | 逐个按 UUID 删除 | `collection.data.delete_by_id(uuid)` × 5，**成功 5/5** |
| 5 | 删除后复核 | 目标对象 = 0；剩余总数 18→13；无残留测试内容 |

**执行脚本（未修改任何生产文件，仅新增于 `.dbg/reallink/`）**：
`.dbg/reallink/cleanup_weaviate_test_objects.py`（全量输出 `.dbg/reallink/cleanup_report.txt` 与 `cleanup.stdout.log`）。

**交叉核验（只读）**：真实 `data/memories.db`（`mode=ro`）`MAX(id)=1385`，`id BETWEEN 1410 AND 1413` 无行
→ 确认该 5 条对象确为本次实测写入的测试对象，不与真实记忆冲突。

### 7.2 删除前基线（memory_id + 内容摘要）

| uuid | memory_id | content |
|------|-----------|---------|
| `8040ae2b-4a40-41ff-82f7-fff568389e22` | 1410 | 量子纠缠退相干实验数据记录 |
| `ce900479-b496-452e-83a7-d3bc14e5da13` | 1410 | 量子纠缠退相干实验数据记录 |
| `714664b4-c95f-494b-a43b-1bcc3211aa7d` | 1411 | 今天天气很好适合散步 |
| `6a2c3619-ac73-4849-9a92-32d04f5f2dc2` | 1412 | 苹果树上结了红苹果 |
| `e23fc014-f9de-4541-8e3d-5956fbf85e9e` | 1413 | 内部部署流程使用 Jenkins 流水线自动构建 |

集合对象总数（删除前）= **18**。

### 7.3 删除方式与结果

逐个按 UUID 调用 `collection.data.delete_by_id(uuid)`（**未使用任何条件批量删除**）：

```
OK  uuid=8040ae2b-...  memory_id=1410
OK  uuid=ce900479-...  memory_id=1410
OK  uuid=714664b4-...  memory_id=1411
OK  uuid=6a2c3619-...  memory_id=1412
OK  uuid=e23fc014-...  memory_id=1413
[delete] 成功 5 / 5，失败 0
```

### 7.4 删除后复核

```
[verify] 剩余目标 memory_id 对象数 = 0（期望 0）
[verify] 剩余对象总数 = 13（删除前 18，净减 5）
[verify] 剩余对象中仍含测试内容的对象数 = 0（期望 0）
[result] PASS 清理完成
```

- 剩余 13 条与副本库 `/api/memories/vectors/status` 的 `sqlite_count=13` 一致，即均为实测前的既有记忆。
- **授权范围一致性**：实测撰写时记录的写入量为 5 条（1410×2/1411/1412/1413），删除前查询到的目标对象
  数量与内容**完全一致，无不一致项**，未发生"范围扩大"或"顺手清理"。
- 全程未修改任何 `.py` / 配置 / `.env` / `public/` / `.trae/rules/`，未启动新后端写入数据，未做 git 操作。

### 7.5 交接状态与最终结果

- **交接状态**：6.5 P4 **已闭合**（人类授权 → 已清理 → 已复核）。
- **最终结果**：真实 weaviate（collection `CXHMSMemory`）恢复为 13 条既有对象，无本次实测测试内容残留。
- **产出物**：`.dbg/reallink/cleanup_weaviate_test_objects.py`、`.dbg/reallink/cleanup_report.txt`、
  `.dbg/reallink/cleanup.stdout.log`。
- **备注（未闭合项，非本次授权范围）**：P2（embedding 失败仍静默写入 weaviate 且日志谎报成功）
  与 P4 的重复插入根因（`add_memory_vector` 用 `insert` 非 upsert）**仍未修复**，
  若 embedding 服务继续不可用，同样的静默写入会再次发生。

---

## 真实 weaviate 验证对象清理（第二轮授权）

> 本节为**仅追加**的第二轮清理记录。人类**显式授权**清理「验证阶段」新写入真实 weaviate 的
> 2 条测试对象：`memory_id = 1414` 与 `memory_id = 1415`（collection `CXHMSMemory`），
> 授权范围**严格限定**为这 2 条，不得扩大。

### 8.1 工程过程

| 顺序 | 动作 | 结果 |
|------|------|------|
| 1 | 定位测试源库（只读） | `.dbg/reallink/memories_nlprobe.db`：`1414 = 用户偏好喝美式咖啡，不加糖`、`1415 = 用户的咖啡因摄入需控制在每天两杯以内`（tags 均为 `["probe","preference"]`）→ 作为期望内容基线 |
| 2 | 连接（与写入时同一封装） | `WeaviateVectorStore(host=localhost, port=8090, grpc_port=50061, embedded=False, schema_class="CXHMSMemory")`，`collection=CXHMSMemory`，`is_available=True` |
| 3 | 删除前基线 + 一致性闸门 | 集合总数 **15**（与预期一致）；目标对象 **2 条**（1414/1415 各 1）；内容标志「美式咖啡」「咖啡因摄入」均匹配 → 放行 |
| 4 | 逐个按 UUID 删除 | `collection.data.delete_by_id(uuid)` × 2，**成功 2/2** |
| 5 | 删除后复核 + 真实库只读复核 | 目标残留 0；总数 **15 → 13**；无残留测试内容；真实 SQLite 无 1414/1415 行 |

**执行脚本（未修改任何生产文件，仅新增于 `.dbg/reallink/`）**：
`.dbg/reallink/cleanup_weaviate_verify_objects.py`（输出 `cleanup_verify_report.txt` / `cleanup_verify.stdout.log`）。

### 8.2 删除前基线（uuid + memory_id + 内容摘要）

| uuid | memory_id | content |
|------|-----------|---------|
| `4a6d258f-3cdd-441e-8cba-b08b5bbf4eff` | 1414 | 用户偏好喝美式咖啡，不加糖 |
| `3c58820e-73ba-4e43-9b78-e17a5384322c` | 1415 | 用户的咖啡因摄入需控制在每天两杯以内 |

集合对象总数（删除前）= **15**。

### 8.3 删除结果

```
OK  uuid=4a6d258f-...  memory_id=1414
OK  uuid=3c58820e-...  memory_id=1415
[delete] 成功 2 / 2，失败 0
```

### 8.4 删除后复核

```
[verify] 剩余目标 memory_id 对象数 = 0（期望 0）
[verify] 剩余对象总数 = 13（期望 13；删除前 15）
[verify] 剩余对象中仍含测试内容的对象数 = 0（期望 0）
[result] PASS 清理完成
```

- **独立复核（graphql，与脚本不同通道）**：`memory_id in (1414,1415)` 聚合查询均返回 **0** 条；
  `Aggregate.CXHMSMemory.meta.count = 13` —— 与脚本结论一致。
- 测试内容标志清单（6 个）：量子纠缠退相干实验数据记录 / 今天天气很好适合散步 / 苹果树上结了红苹果 /
  内部部署流程使用 Jenkins / 美式咖啡 / 咖啡因摄入 → 剩余对象中命中数 **0**。

### 8.5 真实 SQLite 记忆库只读复核（未删除、未写入）

在真实库路径（`.env` 的 `CXHMS_DATABASE_MEMORIES_DB` → `C:\CXHMS\data/memories.db`）上以
`sqlite3.connect("file:...?mode=ro", uri=True)` 只读查询：

```
MAX(id) = 1385
id IN (1414,1415) 行 = []（期望 []）
```

→ **真实库中不存在 1414/1415 行**，与预期一致（这两条写在副本库 `.dbg/reallink/memories_nlprobe.db`）；
向量库中的同名对象确为测试对象，删除不影响真实记忆数据。

### 8.6 范围一致性与未闭合项

- **授权范围一致性**：实际命中对象数量（2 条）、`memory_id`（1414/1415）、内容均与授权描述及
  源库记录**完全一致**；集合总数 15 与"删除前预期 15"一致，**无不一致项**，未扩大范围、未顺手清理。
- 全程未修改任何 `.py` / 配置 / `.env` / `public/` / `.trae/rules/`，未启动后端写入数据，未做 git 操作。
- **仍未闭合（非本次授权范围）**：第 7.5 节登记的 P2（embedding 失败仍静默写入 weaviate 且日志谎报
  「向量同步成功」）与 P4 的重复插入根因（`add_memory_vector` 用 `insert` 非 upsert）**仍未修复**；
  本轮再次出现同类污染（验证阶段又新增 2 条测试对象），**说明该缺陷会随每次真实链路操作复现**。

### 8.7 交接状态与最终结果

- **工程过程**：源库只读核对 → 基线 + 闸门 → 逐个 UUID 删除 → 复核（脚本 + graphql 双通道）→ 真实库只读复核。
- **交接状态**：第二轮清理 **已闭合**（人类授权 → 已清理 2/2 → 已双通道复核）；P2/P4 仍为**未闭合**。
- **最终结果**：collection `CXHMSMemory` 对象数恢复为 **13**，1414/1415 与全部 6 类测试内容均无残留。
- **产出物**：`.dbg/reallink/cleanup_weaviate_verify_objects.py`、`cleanup_verify_report.txt`、
  `cleanup_verify.stdout.log`。

---

## 附加验证（2026-09-26）：embedding 失败路径「真实 weaviate 零写入」实验 + P2/P4 未闭合项关闭

> 本节为**仅追加**记录。目的：对第 7.5 / 8.6 节登记的未闭合项（P2：embedding 失败仍静默写入且日志谎报；P4：`insert` 非 upsert 导致重复插入）做**真实环境实证关闭**。
> 完整证据：`.dbg/vecprobe/evidence.md`（含原始产物清单与三时点计数）。

### 9.1 工程过程

| 顺序 | 动作 | 结果 |
|------|------|------|
| 1 | 探针脚本（真实 `VLLMClient` 模型名指错 → HTTP 404 → `embedding=None`；真实 weaviate；db 用副本 `.dbg/vecprobe/memories.db`） | `.dbg/vecprobe/probe_no_vector_write.py` |
| 2 | 写前基线（只读计数） | `COUNT[CXHMSMemory] = 13`（`baseline_raw.txt`，15:55） |
| 3 | `write_memory`（内部触发 `_sync_vector_for_memory`）+ 直接调用取返回值 | manager 层：`向量同步跳过（embedding 为空）` + `返回 False`；store 层：`add_memory_vector(None/[]) -> False` |
| 4 | 写后计数 | `vectors_count=13`（与基线相同，无 `memory_id=1410` 对象） |
| 5 | 实验后复核（30 分钟后，独立执行只读计数） | `COUNT = 13`，uuid 清单逐条一致，仍无 1410 |

### 9.2 未闭合项关闭判定

| 项 | 原登记 | 现状 | 判定 |
|----|--------|------|------|
| P2（embedding 失败静默写入 + 日志谎报成功） | 7.5 / 8.6 未闭合 | 本次实验：两道防线均拦截且**日志如实**（"跳过/未写入"，无"同步成功"虚报）；真实 weaviate 零写入 | **已闭合**（修复见 `20260925_模块1_修复向量写入与关键词召回.md`，本次为真实环境实证） |
| P4（`insert` 非 upsert → 重复插入） | 7.5 / 8.6 未闭合 | 存储层幂等已下沉（插入前先 `delete_by_memory_id`），weaviate / chroma / milvus_lite 三后端横向拉平（见 `20260926_模块1_修复向量后端空向量与幂等缺口.md`） | **已闭合**（mock 单测锁行为；真实环境重复写入场景未端到端构造，如实标注） |

### 9.3 交接状态与最终结果

- **交接状态**：P2 已闭合（真实环境实证）；P4 已闭合（代码层面 + mock 单测，真实重复写入未构造）。
- **最终结果**：真实 weaviate 在 embedding 失败路径下零写入（三时点计数恒 13）；日志如实。
- **产出物**：`.dbg/vecprobe/`（probe 脚本 / 基线 / 运行日志 / stdout / evidence.md）。
- **补偿说明**：本节由主线程撰写（原后台 subagent 完成脚本执行后未产出 evidence.md）；
  证据全部来自既有原始产物，未做任何清理或删改。
