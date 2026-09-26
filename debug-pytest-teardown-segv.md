# 调试记录：pytest 整目录运行偶发原生崩溃（STATUS_ACCESS_VIOLATION）

- sessionId: `pytest-teardown-segv`
- 现象：`pytest tests/units`（及 `tests/units/test_router.py` 单文件按序运行）偶发原生崩溃
  `exit code 3221225477`（= `0xC0000005` STATUS_ACCESS_VIOLATION），faulthandler 显示
  `Current thread's C stack trace: <cannot get C stack on this system>`（C 层无栈可用）
- 崩点：`tests/units/test_router.py` 第 2 个用例 PASSED 之后（fixture teardown / 下一用例 setup 阶段）
- 历史记录：`current-note.md:499`（2026-07-16）已记录同一退出码，当时归因「C 扩展问题」未修
- 复现率实测（本轮）：`test_router.py` 单文件 **3/5**；`tests/units` 整目录 **1/3**；
  三个用例**各自单独**跑 **0/4**（均不崩）→ 触发条件与「用例顺序 / teardown 时序」相关
- 另一条既有线索：一次组合运行的原生崩溃栈为
  `DedupCheck → get_memory / delete_memory → shutdown.close_all_connections`
  （由代码审查交叉校验 subagent 于本轮前记录）

---

## 一、可证伪假设

### H1 — `DedupCheck` 守护线程与 `close_all_connections` 竞态（主假设）

- **命题**：`write_memory` 每次调用 `_start_async_dedup_check`（manager.py:326）都会 spawn 一个
  **fire-and-forget daemon 线程 `DedupCheck`**；该 worker 之后会 `get_memory` → `_get_connection()`
  使用「该 worker 线程自己」的 sqlite 连接。而 fixture teardown 调 `mm.shutdown()`
  → `close_all_connections()`（manager.py:970）会**关闭并清空**连接池。
  若 worker 在关闭动作前后仍在执行 sqlite 查询 → sqlite3 C 层 use-after-free → ACCESS_VIOLATION。
- **观察点**：上报 `DedupCheck` 线程的 `get_memory`/`_get_connection` 事件时间戳 与
  `close_all_connections` 的时间戳；若存在「close 之后仍有 `DedupCheck` 访问连接」→ 支持 H1。
- **证伪条件**：若禁用去重线程后崩溃率**不下降**（仍 ≥2/5），则 H1 不成立。

### H2 — 跨用例污染（上一个 manager 的残留线程 + 新 manager 构造）

- **命题**：teardown 后旧 manager 的守护线程仍存活，在新用例构造 `MemoryManager` 期间访问旧连接池，
  与 `tmp_path` 变化/文件删除叠加导致崩溃。
- **证伪条件**：若禁用去重线程后崩溃消失，且日志显示崩溃前无其他后台线程存活 → H2 不独立成立（并入 H1）。

### H3 — `asyncio.run` 于共享 ThreadPoolExecutor 线程内（`_run_async_sync`）相关

- **命题**：`_run_async_sync` 在共享 `_get_embedding_executor` 线程中执行 `asyncio.run(coro)`，
  事件循环与 sqlite 连接生命周期交织引发崩溃。
- **证伪条件**：若仅禁用去重线程（而 `_run_async_sync` 的 executor 路径保持不变）即不崩 → H3 非主因。

### H4 — Python 3.14 / sqlite3 C 扩展自身的线程安全缺陷

- **命题**：与业务竞态无关，是 Python 3.14（很新）下 sqlite3 扩展在多线程关闭/使用同一连接时的缺陷。
- **证伪条件**：若业务侧消除竞态后崩溃彻底消失（同一 Python 版本）→ H4 被否定（不是版本 bug）。

---

## 二、环境

| 项 | 值 |
|----|----|
| Debug Server | `python c:\Users\NBLLT666\.trae-cn\builtin_skills\TRAE-debugger\tools\debug-server\python\debug-server.py --session pytest-teardown-segv --outdir c:\CXHMS\.dbg --clean --idle 1800` |
| DEBUG_SERVER_URL | `http://127.0.0.1:7777/event`（`/health` ok） |
| 探针（不改生产代码） | `.dbg/segv/probe_plugin.py`（pytest 插件，monkeypatch 包装 `_get_connection` / `close_all_connections` / `_start_async_dedup_check`，并经 HTTP 上报） |
| 因果开关 | 环境变量 `SEGV_DISABLE_DEDUP=1` → 使 `_start_async_dedup_check` 变为 no-op（仅探针内生效） |
| Python | 3.14（`C:\Python314\python.exe`） |

---

## 三、日志与假设判定

### 实验记录（含失败实验，如实登记）

| 组 | 条件 | 次数 | 崩溃 | 结论 |
|----|------|------|------|------|
| 基线（无任何插件） | `pytest tests/units/test_router.py` | 5 | **3** | 崩溃真实可复现（时有残留 `DedupCheck` 线程） |
| 基线（整目录） | `pytest tests/units` | 3 | **1** | 整目录同样崩 |
| 分用例单跑 | 三个 B8 用例各自单跑 | 各 4 | **0** | 单用例不触发 → 触发条件与「用例顺序 / teardown 时序」相关 |
| A（HTTP 探针启用） | `-p probe_plugin`（上报 `_get_connection` 等） | 4 | 0 | **观察者效应**：探针自身引入同步 HTTP 往返，改变时序，使崩溃消失 |
| B（禁用去重线程，无上报） | `-p nodup_plugin` | 6 | 0 | — |
| 对照（无插件，B 组之后紧接测量） | 同基线命令 | 4 | **0** | 对照也变为 0 → **实验失去分辨力** |

**实验结论：无法用统计方法判定因果**。原因：崩溃率随机器负载/时序剧烈波动（基线先 3/5 后 0/4），
且任何探针（哪怕仅 no-op 或一次 HTTP 上报）都会改变时序并掩盖崩溃。
故本轮**放弃「统计证明某次崩溃的归因」**，转为按「消除确定性的 use-after-free 结构风险」修复
（该风险客观存在，与崩溃是否概率性无关）。

### 假设判定

| 假设 | 判定 | 依据 |
|------|------|------|
| **H1** `DedupCheck` 守护线程与 `close_all_connections` 竞态 | **成立（结构性证据链）**，未获统计证明 | ① `_start_async_dedup_check` 每次 write 都 spawn 不可追踪的 daemon 线程；② worker 会经 `get_memory` / `delete_memory` / 去重检索使用**本线程自己的** sqlite 连接；③ `shutdown()` 原先**完全不等待**这些 worker 就 `close_all_connections()`；④ 崩点恰在 teardown/setup 窗口；⑤ 历史栈 `DedupCheck → get_memory/delete_memory → shutdown.close_all_connections`；⑥ 单用例 0/4 vs 按序 3/5 |
| H2 跨用例污染（上一 manager 残留线程） | **并入 H1** | B 组禁用去重线程后 0/6；且 H1 的修复（shutdown 等待 + worker 早退）同时消除了「残留线程跨用例存在」这一形式 |
| H3 `_run_async_sync` 于共享 executor 内 `asyncio.run` | **未证实，非主因** | B 组仅禁用去重线程（executor 路径不变）即 0/6；但受观察者效应限制，不能排除其贡献 |
| H4 Python 3.14 / sqlite3 C 扩展自身缺陷 | **未证实，倾向否定** | 未更换 Python 版本的前提下，业务侧消除竞态后 12 次单文件 + 3 次整目录均 0 崩溃；但同样受"非确定性"限制，不宣称已证明 |

## 四、结论与修复

**结论**：这是一个**确定性的结构性 use-after-free 风险**（fire-and-forget 守护线程使用会在
`shutdown()` 中被关闭并清空的 sqlite 连接池），其外在表现为概率性的原生崩溃。
历史记录（`current-note.md` 2026-07-16）把它归为「C 扩展问题」，本轮纠正为**业务侧线程生命周期缺陷**
（未更换 Python 版本即显著改善，且机制可复现于代码结构）。

**修复**（仅动 `backend/core/memory/manager.py` 三处，详见变更文档
`.trae/documents/20260926_模块1_修复后台去重线程与连接池关闭竞态.md`）：

1. `__init__` 新增 `self._dedup_threads` 登记表；
2. `_start_async_dedup_check`：worker 开头 `_stop_event` 早退（关闭中不再发起 DB 访问）；
   线程登记后启动；worker `finally` 自我注销；
3. `shutdown()`：新增 `_join_dedup_threads(timeout=5)`，在 `close_all_connections()` **之前**
   join 在途 worker（不持锁 join，避免与 worker 自我注销互等），并兜底清理已结束的登记项。

**修复后验证（置信度检查，非统计证明）**：

| 验证 | 结果 |
|------|------|
| `pytest tests/units/test_router.py` 连续 12 次 | **0/12 崩溃** |
| `pytest tests/units` 整目录 连续 3 次 | **0/3 崩溃**，每次 `141 passed` |
| `pytest tests/contracts` | 620 passed |
| `pytest tests/simulation` | 50 passed, 1 skipped |
| 确定性单测 `tests/units/test_dedup_thread_lifecycle.py` | 3 passed（断言：关闭连接池**晚于** worker 结束；关闭中 worker 不访问 DB；登记表不泄漏） |

**未彻底闭环的部分（如实标注）**：崩溃的「统计证明」不可得（观察者效应）；
`_run_async_sync` 的共享 executor 路径（H3）未单独排除，仍作为潜在贡献项留在观察清单。
