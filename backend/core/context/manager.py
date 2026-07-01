import asyncio
import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from backend.core.exceptions import ContextError
from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)


class ContextManager:
    """上下文管理器

    负责管理对话会话和消息历史，使用文件+内存双存储方案。
    每个 agent 一个 JSON 文件，内存中维护完整副本。

    Attributes:
        db_path: 兼容参数，实际使用 data/context/ 目录
    """

    def __init__(self, db_path: str = "data/sessions.db") -> None:
        """初始化上下文管理器

        Args:
            db_path: 兼容参数，忽略，改用 data/context/ 目录
        """
        self._context_dir = "data/context"
        self._lock = threading.Lock()
        self._store: Dict[str, Dict] = {}

        os.makedirs(self._context_dir, exist_ok=True)
        self._load_from_disk()

    # ─── 内部工具方法 ────────────────────────────────────────────

    def _session_file(self, session_id: str) -> str:
        """获取 session 对应的 JSON 文件路径"""
        return os.path.join(self._context_dir, f"{session_id}.json")

    def _atomic_write(self, session_id: str, data: Dict) -> None:
        """原子写入：先写 .tmp 再 os.replace"""
        file_path = self._session_file(session_id)
        tmp_path = file_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, file_path)

    def _load_from_disk(self) -> None:
        """启动时从 data/context/ 加载所有 .json 文件到内存"""
        if not os.path.isdir(self._context_dir):
            return
        for filename in os.listdir(self._context_dir):
            if not filename.endswith(".json"):
                continue
            file_path = os.path.join(self._context_dir, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                session_id = filename[:-5]  # 去掉 .json
                self._store[session_id] = data
            except Exception as e:
                logger.warning(f"加载上下文文件失败 {file_path}: {e}")

    def _persist(self, session_id: str) -> None:
        """将内存中的 session 数据持久化到文件（调用方需持有锁或在锁外安全调用）"""
        data = self._store.get(session_id)
        if data is not None:
            self._atomic_write(session_id, data)

    # ─── 兼容方法（无操作）────────────────────────────────────────

    def shutdown(self):
        """关闭（兼容，无操作）"""
        pass

    def clear_cache(self):
        """清理缓存（兼容，无操作）"""
        pass

    def close_connection(self):
        """关闭连接（兼容，无操作）"""
        pass

    # ─── Session CRUD ─────────────────────────────────────────────

    def create_session(
        self,
        workspace_id: str = "default",
        title: str = "",
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """创建会话

        Args:
            workspace_id: 工作区ID
            title: 会话标题
            user_id: 用户ID
            metadata: 元数据
            session_id: 自定义会话ID（可选）

        Returns:
            会话ID
        """
        session_id = session_id or str(uuid.uuid4())
        now = datetime.now().isoformat()

        session_data = {
            "id": session_id,
            "workspace_id": workspace_id,
            "title": title or "新对话",
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
            "summary": None,
            "metadata": metadata or {},
            "is_active": True,
        }

        entry = {
            "session": session_data,
            "messages": [],
            "mono_contexts": [],
        }

        with self._lock:
            self._store[session_id] = entry
            self._persist(session_id)

        logger.info(f"会话已创建: id={session_id}")
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        """从内存取 session 元数据"""
        entry = self._store.get(session_id)
        if entry:
            return dict(entry["session"])
        return None

    def get_sessions(
        self, workspace_id: str = "default", limit: int = 20, active_only: bool = True
    ) -> List[Dict]:
        """返回 session 列表"""
        results = []
        for entry in self._store.values():
            session = entry["session"]
            if session.get("workspace_id") != workspace_id:
                continue
            if active_only and not session.get("is_active", True):
                continue
            results.append(dict(session))

        results.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return results[:limit]

    def update_session(self, session_id: str, **kwargs) -> bool:
        """更新 session 字段，写文件"""
        with self._lock:
            entry = self._store.get(session_id)
            if not entry:
                return False

            session = entry["session"]
            updated = False
            for key in ("title", "summary", "is_active", "metadata", "workspace_id", "user_id"):
                if key in kwargs:
                    session[key] = kwargs[key]
                    updated = True

            if updated:
                session["updated_at"] = datetime.now().isoformat()
                self._persist(session_id)

        return updated

    def delete_session(self, session_id: str) -> bool:
        """从内存和文件中删除 session"""
        with self._lock:
            if session_id not in self._store:
                return False

            del self._store[session_id]
            file_path = self._session_file(session_id)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.warning(f"删除会话文件失败 {file_path}: {e}")

        return True

    def clear_all_sessions(self) -> int:
        """清空所有内存和文件

        Returns:
            删除的会话数量
        """
        with self._lock:
            count = len(self._store)
            self._store.clear()

            # 删除目录下所有 .json 文件
            if os.path.isdir(self._context_dir):
                for filename in os.listdir(self._context_dir):
                    if filename.endswith(".json"):
                        try:
                            os.remove(os.path.join(self._context_dir, filename))
                        except Exception as e:
                            logger.warning(f"删除文件失败 {filename}: {e}")

        return count

    def list_sessions(self) -> List[Dict]:
        """返回所有 session 列表（用于 agents.py 的 get_agent_stats）"""
        return [dict(entry["session"]) for entry in self._store.values()]

    # ─── Message 操作 ─────────────────────────────────────────────

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        content_type: str = "text",
        metadata: Dict = None,
        tokens: int = 0,
    ) -> str:
        """追加消息到列表，更新 session.message_count 和 updated_at，同步写文件"""
        message_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        msg_meta = metadata or {}

        message = {
            "id": message_id,
            "role": role,
            "content": content,
            "content_type": content_type,
            "metadata": msg_meta,
            "tokens": tokens,
            "created_at": now,
            "is_deleted": False,
            "thinking": msg_meta.get("thinking"),
            "images": msg_meta.get("images"),
        }

        with self._lock:
            entry = self._store.get(session_id)
            if not entry:
                raise ContextError(f"Session {session_id} not found")

            entry["messages"].append(message)
            entry["session"]["message_count"] += 1
            entry["session"]["updated_at"] = now
            self._persist(session_id)

        return message_id

    async def add_message_async(
        self,
        session_id: str,
        role: str,
        content: str,
        content_type: str = "text",
        metadata: Dict = None,
        tokens: int = 0,
    ) -> str:
        """异步追加消息：内存立即更新（持锁），磁盘持久化通过 asyncio.to_thread 卸载，不阻塞事件循环。

        与 add_message 行为一致，但将磁盘写入卸载到线程池，避免阻塞事件循环。
        磁盘写入失败仅记录日志，不抛出异常（不打断流式响应）。
        """
        message_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        msg_meta = metadata or {}

        message = {
            "id": message_id,
            "role": role,
            "content": content,
            "content_type": content_type,
            "metadata": msg_meta,
            "tokens": tokens,
            "created_at": now,
            "is_deleted": False,
            "thinking": msg_meta.get("thinking"),
            "images": msg_meta.get("images"),
        }

        with self._lock:
            entry = self._store.get(session_id)
            if not entry:
                raise ContextError(f"Session {session_id} not found")

            entry["messages"].append(message)
            entry["session"]["message_count"] += 1
            entry["session"]["updated_at"] = now
            # Capture a snapshot for disk persistence (avoid holding lock during I/O)
            snapshot = dict(entry["session"])
            messages_snapshot = list(entry["messages"])
            mono_contexts_snapshot = list(entry.get("mono_contexts", []))

        # Disk persistence offloaded to thread pool (outside the lock)
        try:
            await asyncio.to_thread(
                self._atomic_write,
                session_id,
                {
                    "session": snapshot,
                    "messages": messages_snapshot,
                    "mono_contexts": mono_contexts_snapshot,
                },
            )
        except Exception as e:
            logger.warning(f"异步持久化失败 {session_id}: {e}")

        return message_id

    def get_messages(
        self, session_id: str, limit: int = 50, offset: int = 0, include_deleted: bool = False
    ) -> List[Dict]:
        """从内存列表取消息

        limit 取最后 N 条，offset 从最旧的消息跳过，返回从旧到新顺序。
        过滤 is_deleted。
        """
        entry = self._store.get(session_id)
        if not entry:
            return []

        all_msgs = entry["messages"]

        # 过滤已删除
        if not include_deleted:
            filtered = [m for m in all_msgs if not m.get("is_deleted", False)]
        else:
            filtered = list(all_msgs)

        # offset 从最旧的消息跳过，limit 取最后 N 条
        total = len(filtered)
        start = offset
        end = total
        sliced = filtered[start:end]

        # 如果超过 limit，只取最后 limit 条
        if len(sliced) > limit:
            sliced = sliced[-limit:]

        return [dict(m) for m in sliced]

    def delete_message(self, message_id: str) -> bool:
        """找到消息标记 is_deleted=True，减少 message_count，写文件"""
        with self._lock:
            for session_id, entry in self._store.items():
                for msg in entry["messages"]:
                    if msg["id"] == message_id and not msg.get("is_deleted", False):
                        msg["is_deleted"] = True
                        entry["session"]["message_count"] = max(
                            0, entry["session"]["message_count"] - 1
                        )
                        entry["session"]["updated_at"] = datetime.now().isoformat()
                        self._persist(session_id)
                        return True
        return False

    def get_message_count(self, session_id: str) -> int:
        """返回未删除消息数"""
        entry = self._store.get(session_id)
        if not entry:
            return 0
        return sum(1 for m in entry["messages"] if not m.get("is_deleted", False))

    def clear_session_messages(self, session_id: str) -> bool:
        """标记所有消息 is_deleted=True，重置 message_count=0，写文件"""
        with self._lock:
            entry = self._store.get(session_id)
            if not entry:
                return False

            for msg in entry["messages"]:
                msg["is_deleted"] = True

            entry["session"]["message_count"] = 0
            entry["session"]["updated_at"] = datetime.now().isoformat()
            self._persist(session_id)

        return True

    # ─── 统计 ─────────────────────────────────────────────────────

    def get_statistics(self, workspace_id: str = "default") -> Dict:
        """遍历内存中所有 session 统计"""
        total_sessions = 0
        active_sessions = 0
        total_messages = 0

        for entry in self._store.values():
            session = entry["session"]
            if session.get("workspace_id") != workspace_id:
                continue

            total_sessions += 1
            if session.get("is_active", True):
                active_sessions += 1

            total_messages += sum(1 for m in entry["messages"] if not m.get("is_deleted", False))

        avg_messages = total_messages / total_sessions if total_sessions > 0 else 0

        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "total_messages": total_messages,
            "avg_messages_per_session": round(avg_messages, 2),
        }

    # ─── Mono 上下文 ──────────────────────────────────────────────

    def add_mono_context(
        self, session_id: str, content: str, rounds: int = 1, metadata: Dict = None
    ) -> bool:
        """追加 mono 上下文，写文件"""
        try:
            now = datetime.now()
            expires_at = now + timedelta(hours=rounds)

            mono = {
                "id": str(uuid.uuid4()),
                "content": content,
                "metadata": {
                    **(metadata or {}),
                    "expires_at": expires_at.isoformat(),
                    "rounds": rounds,
                },
                "created_at": now.isoformat(),
                "is_deleted": False,
            }

            with self._lock:
                entry = self._store.get(session_id)
                if not entry:
                    raise ContextError(f"Session {session_id} not found")

                entry["mono_contexts"].append(mono)
                entry["session"]["updated_at"] = now.isoformat()
                self._persist(session_id)

            logger.info(f"Mono上下文已添加: session_id={session_id}, rounds={rounds}")
            return True
        except ContextError:
            raise
        except Exception as e:
            logger.error(f"添加Mono上下文失败: {e}")
            return False

    def get_mono_context(self, session_id: str) -> List[Dict]:
        """返回未过期且未删除的 mono 上下文"""
        entry = self._store.get(session_id)
        if not entry:
            return []

        now = datetime.now()
        valid = []

        for mono in entry["mono_contexts"]:
            if mono.get("is_deleted", False):
                continue
            meta = mono.get("metadata", {})
            expires_at_str = meta.get("expires_at")
            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    if expires_at > now:
                        valid.append(dict(mono))
                except Exception:
                    pass

        return valid

    def clear_expired_mono(self, session_id: str = None) -> int:
        """标记过期 mono 为 is_deleted，写文件"""
        now = datetime.now()
        deleted_count = 0

        with self._lock:
            targets = (
                {session_id: self._store[session_id]}
                if session_id and session_id in self._store
                else self._store
            )

            for sid, entry in targets.items():
                changed = False
                for mono in entry["mono_contexts"]:
                    if mono.get("is_deleted", False):
                        continue
                    meta = mono.get("metadata", {})
                    expires_at_str = meta.get("expires_at")
                    if expires_at_str:
                        try:
                            expires_at = datetime.fromisoformat(expires_at_str)
                            if expires_at <= now:
                                mono["is_deleted"] = True
                                deleted_count += 1
                                changed = True
                        except Exception:
                            pass

                if changed:
                    self._persist(sid)

        if deleted_count > 0:
            logger.info(f"清理了 {deleted_count} 条过期Mono上下文")

        return deleted_count

    # ─── AgentContextManager 兼容方法 ──────────────────────────────

    def append_message(self, agent_id: str, role: str, content: str, metadata: Dict = None) -> str:
        """等同于 add_message，但参数名不同"""
        return self.add_message(
            session_id=agent_id,
            role=role,
            content=content,
            content_type="text",
            metadata=metadata,
            tokens=0,
        )

    def get_message_history(self, agent_id: str, limit: int = 100) -> List[Dict]:
        """等同于 get_messages"""
        return self.get_messages(session_id=agent_id, limit=limit, offset=0, include_deleted=False)

    def get_context_summary(self, agent_id: str) -> Dict:
        """返回该 agent 的上下文摘要"""
        entry = self._store.get(agent_id)
        if not entry:
            return {"agent_id": agent_id, "exists": False}

        session = entry["session"]
        messages = entry["messages"]
        mono_contexts = entry["mono_contexts"]

        active_messages = [m for m in messages if not m.get("is_deleted", False)]
        active_mono = [m for m in mono_contexts if not m.get("is_deleted", False)]

        return {
            "agent_id": agent_id,
            "exists": True,
            "title": session.get("title", ""),
            "created_at": session.get("created_at", ""),
            "updated_at": session.get("updated_at", ""),
            "message_count": len(active_messages),
            "mono_context_count": len(active_mono),
            "is_active": session.get("is_active", True),
        }

    def clear_context(self, agent_id: str) -> bool:
        """等同于 clear_session_messages + 删除 session"""
        self.clear_session_messages(agent_id)
        return self.delete_session(agent_id)

    def update_last_active(self, agent_id: str) -> None:
        """更新 session.updated_at"""
        with self._lock:
            entry = self._store.get(agent_id)
            if entry:
                entry["session"]["updated_at"] = datetime.now().isoformat()
                self._persist(agent_id)

    def cleanup_old_messages(self, agent_id: str, keep_count: int = 1000) -> None:
        """保留最近 keep_count 条，标记其余 is_deleted"""
        with self._lock:
            entry = self._store.get(agent_id)
            if not entry:
                return

            active_msgs = [m for m in entry["messages"] if not m.get("is_deleted", False)]
            if len(active_msgs) <= keep_count:
                return

            # 需要删除的数量
            to_delete = len(active_msgs) - keep_count
            deleted = 0

            for msg in entry["messages"]:
                if deleted >= to_delete:
                    break
                if not msg.get("is_deleted", False):
                    msg["is_deleted"] = True
                    deleted += 1

            entry["session"]["message_count"] = max(
                0, entry["session"]["message_count"] - deleted
            )
            entry["session"]["updated_at"] = datetime.now().isoformat()
            self._persist(agent_id)

    # ─── 日记式摘要与上下文替换 ──────────────────────────────────

    def get_summarizable_range(self, session_id: str) -> Dict[str, Any]:
        """返回可摘要的消息范围

        从已摘要位置到末尾，排除当前未完成话题（若最后一条是 user 消息且无 assistant 回复）。

        Returns:
            {"start": int, "end": int, "total": int, "has_unfinished_topic": bool}
        """
        entry = self._store.get(session_id)
        if not entry:
            return {"start": 0, "end": 0, "total": 0, "has_unfinished_topic": False}

        messages = entry["messages"]
        active = [m for m in messages if not m.get("is_deleted", False)]

        if not active:
            return {"start": 0, "end": 0, "total": 0, "has_unfinished_topic": False}

        # 优先通过 diary_summary 标记确定起始位置（替换后插入的摘要消息）
        start = 0
        for i, m in enumerate(active):
            meta = m.get("metadata") or {}
            if m.get("content_type") == "diary_summary" or meta.get("is_diary_summary"):
                start = i + 1
                break

        # 若未找到 diary_summary 标记，回退到 summarized_up_to
        if start == 0:
            summarized_up_to = entry["session"].get("summarized_up_to", 0)
            start = min(summarized_up_to, len(active))

        # 话题完成度判定：最后一条是 user 消息 → 当前话题未完成
        has_unfinished_topic = active[-1].get("role") == "user"

        if has_unfinished_topic and len(active) > 1:
            end = len(active) - 1  # 排除最后一条未回复的 user 消息
        else:
            end = len(active)

        if start > end:
            start = end

        return {
            "start": start,
            "end": end,
            "total": len(active),
            "has_unfinished_topic": has_unfinished_topic,
        }

    def replace_messages_with_summary(
        self,
        session_id: str,
        summary_entries: List[str],
        summarized_up_to_index: int,
    ) -> bool:
        """将被摘要的原始消息替换为摘要内容

        - 标记 [0, summarized_up_to_index) 范围内的活跃消息为已删除
        - 在消息列表头部插入多条 diary_summary 标记的摘要消息（每条摘要一篇）
        - 更新 session["summarized_up_to"] 记录已摘要范围，避免重复摘要
        - 持久化 session JSON 文件

        Args:
            session_id: 会话ID
            summary_entries: 摘要文本列表（每篇日记正文）。向后兼容：传入单个字符串时按单条处理。
            summarized_up_to_index: 被摘要的消息数量（活跃消息索引，不含）

        Returns:
            是否成功
        """
        # 向后兼容：单个字符串视为单条列表
        if isinstance(summary_entries, str):
            summary_entries = [summary_entries]

        with self._lock:
            entry = self._store.get(session_id)
            if not entry:
                return False

            messages = entry["messages"]
            active_indices = [
                i for i, m in enumerate(messages) if not m.get("is_deleted", False)
            ]

            # 标记前 summarized_up_to_index 条活跃消息为已删除
            to_delete = min(summarized_up_to_index, len(active_indices))
            for i in range(to_delete):
                messages[active_indices[i]]["is_deleted"] = True

            # 从被摘要的消息中提取话题起止时间
            start_time = None
            end_time = None
            for i in range(to_delete):
                msg = messages[active_indices[i]]
                msg_time_str = msg.get("created_at")
                if msg_time_str:
                    try:
                        # 尝试解析 ISO 格式时间
                        msg_time = datetime.fromisoformat(msg_time_str)
                    except (ValueError, TypeError):
                        msg_time = datetime.now()
                else:
                    msg_time = datetime.now()
                if start_time is None or msg_time < start_time:
                    start_time = msg_time
                if end_time is None or msg_time > end_time:
                    end_time = msg_time
            # fallback：若无被摘要消息，用当前时间
            if start_time is None:
                start_time = datetime.now()
            if end_time is None:
                end_time = datetime.now()
            start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

            # 统计同一天已有的 diary_summary 数量，分配当日递增序号
            today_str = datetime.now().strftime("%Y-%m-%d")
            same_day_count = 0
            for m in messages:
                if m.get("content_type") == "diary_summary" and not m.get("is_deleted", False):
                    meta = m.get("metadata", {})
                    # 优先从 time_range.start 取日期，否则从 created_at 取
                    tr = meta.get("time_range", {})
                    date_source = tr.get("start") or m.get("created_at", "")
                    if date_source:
                        try:
                            dt = datetime.fromisoformat(date_source)
                            if dt.strftime("%Y-%m-%d") == today_str:
                                same_day_count += 1
                        except (ValueError, TypeError):
                            pass
            sequence = same_day_count + 1

            # 在列表头部插入多条摘要消息（每条摘要一篇，保持传入顺序）
            now = datetime.now().isoformat()
            summary_messages = []
            for idx, summary_text in enumerate(summary_entries):
                # 仅第一条摘要使用当前计算的 sequence，后续递增
                cur_sequence = sequence + idx
                prefix = f"[上下文摘要 | 时间范围: {start_str} ~ {end_str} | 当日第{cur_sequence}次摘要]\n"
                summary_messages.append({
                    "id": str(uuid.uuid4()),
                    "role": "system",
                    "content": prefix + summary_text,
                    "content_type": "diary_summary",
                    "metadata": {
                        "is_diary_summary": True,
                        "summarized_up_to": summarized_up_to_index,
                        "time_range": {"start": start_str, "end": end_str},
                        "sequence": cur_sequence,
                    },
                    "tokens": 0,
                    "created_at": now,
                    "is_deleted": False,
                })
            messages[0:0] = summary_messages

            # 更新 session 元数据
            entry["session"]["summarized_up_to"] = summarized_up_to_index
            entry["session"]["message_count"] = sum(
                1 for m in messages if not m.get("is_deleted", False)
            )
            entry["session"]["updated_at"] = now
            self._persist(session_id)

        logger.info(
            f"上下文已替换为日记摘要: session={session_id}, 已摘要 {to_delete} 条消息, 摘要条目 {len(summary_messages)} 篇"
        )
        return True
