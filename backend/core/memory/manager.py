from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
import json
import threading
import time
from backend.core.exceptions import DatabaseError, MemoryError, VectorStoreError
from backend.core.logging_config import get_contextual_logger

try:
    import orjson
    def json_dumps(obj, **kwargs):
        return orjson.dumps(obj).decode('utf-8')
    def json_loads(s, **kwargs):
        return orjson.loads(s)
except ImportError:
    import json
    def json_dumps(obj, **kwargs):
        return json.dumps(obj, **kwargs)
    def json_loads(s, **kwargs):
        return json.loads(s, **kwargs)

logger = get_contextual_logger(__name__)


class MemoryManager:
    """记忆管理器
    
    负责记忆的创建、查询、更新、删除等操作，支持向量搜索和衰减计算
    
    Attributes:
        db_path: 数据库文件路径
        _vector_store: 向量存储实例
        _embedding_model: 嵌入模型实例
        _hybrid_search: 混合搜索实例
    """
    
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str = "data/memories.db") -> "MemoryManager":
        """创建单例实例
        
        Args:
            db_path: 数据库文件路径
            
        Returns:
            MemoryManager实例
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = "data/memories.db") -> None:
        """初始化记忆管理器
        
        Args:
            db_path: 数据库文件路径
        """
        if self._initialized:
            return

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._local = threading.local()
        self._connection_pool: Dict[int, Dict] = {}

        self._vector_store = None
        self._embedding_model = None
        self._hybrid_search = None

        self._init_db()

        self._stop_event = threading.Event()
        self._cleanup_thread = None
        self._start_cleanup_task()

        logger.info(f"记忆管理器初始化完成: db={db_path}")
        self._initialized = True

    def _start_cleanup_task(self):
        def cleanup_task():
            while not self._stop_event.wait(60):
                try:
                    self._cleanup_idle_connections()
                    self._check_vector_store_health()
                except Exception as e:
                    logger.warning(f"清理任务异常: {e}")
            logger.info("清理任务已停止")

        self._cleanup_thread = threading.Thread(
            target=cleanup_task,
            daemon=True,
            name="MemoryCleanup"
        )
        self._cleanup_thread.start()

    def _cleanup_idle_connections(self):
        idle_threshold = time.time() - 300
        with self._lock:
            idle_threads = [
                tid for tid, conn_info in self._connection_pool.items()
                if isinstance(conn_info, dict) and conn_info.get('last_used', 0) < idle_threshold
            ] + [
                tid for tid, conn in self._connection_pool.items()
                if not isinstance(conn, dict) and getattr(conn, '_last_used', 0) < idle_threshold
            ]
            for tid in idle_threads:
                try:
                    conn_info = self._connection_pool[tid]
                    if isinstance(conn_info, dict):
                        conn_info['connection'].close()
                    else:
                        conn_info.close()
                except Exception:
                    pass
                del self._connection_pool[tid]
            if idle_threads:
                logger.info(f"清理了 {len(idle_threads)} 个空闲连接")

    def _check_vector_store_health(self):
        if self._vector_store:
            try:
                if not self._vector_store.is_available():
                    logger.warning("向量存储不可用，重置连接")
                    self._vector_store = None
            except Exception as e:
                logger.warning(f"向量存储健康检查失败: {e}")
                self._vector_store = None

    def shutdown(self):
        logger.info("正在关闭记忆管理器...")
        self._stop_event.set()

        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)

        self.close_all_connections()

        if self._vector_store:
            try:
                self._vector_store.close()
            except Exception as e:
                logger.warning(f"关闭向量存储失败: {e}")
            self._vector_store = None

        logger.info("记忆管理器已关闭")

    def _init_db(self):
        import sqlite3
        conn = sqlite3.connect(str(self.db_path), timeout=20.0)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                vector_id VARCHAR(100),
                metadata TEXT,
                importance INTEGER DEFAULT 3,
                importance_score FLOAT DEFAULT 0.6,
                decay_type VARCHAR(20) DEFAULT 'exponential',
                decay_params TEXT,
                reactivation_count INTEGER DEFAULT 0,
                emotion_score FLOAT DEFAULT 0.0,
                permanent BOOLEAN DEFAULT FALSE,
                psychological_age FLOAT DEFAULT 1.0,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                archived_at TIMESTAMP,
                is_deleted BOOLEAN DEFAULT FALSE,
                source VARCHAR(50) DEFAULT 'user',
                workspace_id VARCHAR(100) DEFAULT 'default'
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation VARCHAR(50) NOT NULL,
                memory_id INTEGER,
                session_id VARCHAR(36),
                operator VARCHAR(20) NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS permanent_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                importance_score FLOAT DEFAULT 1.0,
                emotion_score FLOAT DEFAULT 0.0,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                metadata TEXT,
                source VARCHAR(50) DEFAULT 'user',
                verified BOOLEAN DEFAULT TRUE
            )
        ''')

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type)",
            "CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_memories_is_deleted ON memories(is_deleted)",
            "CREATE INDEX IF NOT EXISTS idx_memories_permanent ON memories(permanent)",
            "CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance)",
            "CREATE INDEX IF NOT EXISTS idx_memories_workspace ON memories(workspace_id)"
        ]
        for idx in indexes:
            cursor.execute(idx)

        conn.commit()
        conn.close()

    def _get_connection(self):
        import sqlite3
        thread_id = threading.get_ident()

        with self._lock:
            if thread_id in self._connection_pool:
                conn_info = self._connection_pool[thread_id]
                if isinstance(conn_info, dict):
                    conn = conn_info['connection']
                else:
                    conn = conn_info

                try:
                    conn.execute("SELECT 1")
                    if isinstance(conn_info, dict):
                        conn_info['last_used'] = time.time()
                    return conn
                except Exception as e:
                    logger.warning(f"验证连接池连接失败: {e}")

                try:
                    if isinstance(conn_info, dict):
                        conn_info['connection'].close()
                    else:
                        conn.close()
                except Exception as e:
                    logger.warning(f"关闭旧连接失败: {e}")
                del self._connection_pool[thread_id]

        try:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=20.0,
                check_same_thread=False
            )
        except sqlite3.Error as e:
            logger.error(f"数据库连接失败: {e}")
            raise

        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")

        connection_info = {
            'connection': conn,
            'last_used': time.time()
        }

        with self._lock:
            self._connection_pool[thread_id] = connection_info

        return conn

    def close_all_connections(self):
        with self._lock:
            for thread_id, conn_info in list(self._connection_pool.items()):
                try:
                    if isinstance(conn_info, dict):
                        conn_info['connection'].close()
                    else:
                        conn_info.close()
                except Exception as e:
                    logger.warning(f"关闭连接失败: {e}")
            self._connection_pool.clear()

    def write_memory(
        self,
        content: str,
        memory_type: str = "long_term",
        importance: int = 3,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
        permanent: bool = False,
        emotion_score: float = 0.0,
        workspace_id: str = "default"
    ) -> int:
        """写入记忆
        
        Args:
            content: 记忆内容
            memory_type: 记忆类型（long_term, short_term, permanent）
            importance: 重要性等级（1-5）
            tags: 标签列表
            metadata: 元数据
            permanent: 是否为永久记忆
            emotion_score: 情感分数
            workspace_id: 工作区ID
            
        Returns:
            记忆ID
            
        Raises:
            DatabaseError: 数据库操作失败
        """
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                cursor.execute('''
                    INSERT INTO memories (
                        type, content, importance, importance_score,
                        decay_type, decay_params, reactivation_count,
                        emotion_score, permanent, psychological_age,
                        tags, metadata, created_at, workspace_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    memory_type,
                    content,
                    importance,
                    0.6 if not permanent else 1.0,
                    "zero" if permanent else "exponential",
                    json_dumps({}),
                    0,
                    emotion_score,
                    permanent,
                    1.0,
                    json_dumps(tags or [], ensure_ascii=False),
                    json_dumps(metadata or {}, ensure_ascii=False),
                    datetime.now().isoformat(),
                    workspace_id
                ))

                memory_id = cursor.lastrowid

                cursor.execute('''
                    INSERT INTO audit_logs (operation, memory_id, operator, details)
                    VALUES (?, ?, ?, ?)
                ''', ("create", memory_id, "system", json_dumps({"type": memory_type})))

                conn.commit()
                logger.info(f"记忆已写入: id={memory_id}, type={memory_type}")
                return memory_id
            finally:
                conn.close()

    def get_memory(self, memory_id: int, include_deleted: bool = False) -> Optional[Dict]:
        """获取记忆
        
        Args:
            memory_id: 记忆ID
            include_deleted: 是否包含已删除的记忆
            
        Returns:
            记忆字典，如果不存在则返回None
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = "SELECT * FROM memories WHERE id = ?"
            if not include_deleted:
                query += " AND is_deleted = FALSE"

            cursor.execute(query, (memory_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_memory(row)
            return None
        finally:
            conn.close()

    def search_memories(
        self,
        query: Optional[str] = None,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        time_range: Optional[str] = None,
        limit: int = 10,
        include_deleted: bool = False,
        workspace_id: str = "default"
    ) -> List[Dict]:
        """搜索记忆
        
        Args:
            query: 搜索关键词
            memory_type: 记忆类型
            tags: 标签列表
            time_range: 时间范围（today, last_week, last_month）
            limit: 返回数量限制
            include_deleted: 是否包含已删除的记忆
            workspace_id: 工作区ID
            
        Returns:
            记忆列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            conditions = ["workspace_id = ?"]
            params = [workspace_id]

            if query:
                conditions.append("content LIKE ?")
                params.append(f"%{query}%")

            if memory_type:
                conditions.append("type = ?")
                params.append(memory_type)

            if tags:
                for tag in tags:
                    conditions.append("tags LIKE ?")
                    params.append(f'%"{tag}"%')

            if time_range:
                from datetime import timedelta
                now = datetime.now()
                if time_range == "today":
                    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                elif time_range == "last_week":
                    start_time = now - timedelta(days=7)
                elif time_range == "last_month":
                    start_time = now - timedelta(days=30)
                else:
                    start_time = now - timedelta(days=1)
                conditions.append("created_at >= ?")
                params.append(start_time.isoformat())

            if not include_deleted:
                conditions.append("is_deleted = FALSE")

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)

            cursor.execute(
                f"SELECT * FROM memories WHERE {where_clause} ORDER BY importance DESC, created_at DESC LIMIT ?",
                params
            )

            rows = cursor.fetchall()
            return [self._row_to_memory(row) for row in rows]
        finally:
            conn.close()

    def update_memory(
        self,
        memory_id: int,
        new_content: str = None,
        new_tags: List[str] = None,
        new_importance: int = None,
        new_metadata: Dict = None
    ) -> bool:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                updates = []
                params = []

                if new_content is not None:
                    updates.append("content = ?")
                    params.append(new_content)

                if new_tags is not None:
                    updates.append("tags = ?")
                    params.append(json_dumps(new_tags, ensure_ascii=False))

                if new_importance is not None:
                    updates.append("importance = ?")
                    params.append(new_importance)

                if new_metadata is not None:
                    updates.append("metadata = ?")
                    params.append(json_dumps(new_metadata, ensure_ascii=False))

                if not updates:
                    return False

                updates.append("updated_at = ?")
                params.append(datetime.now().isoformat())
                params.append(memory_id)

                query = f"UPDATE memories SET {', '.join(updates)} WHERE id = ? AND is_deleted = FALSE"
                cursor.execute(query, params)

                success = cursor.rowcount > 0
                conn.commit()
                return success
            finally:
                conn.close()

    def delete_memory(self, memory_id: int, soft_delete: bool = True) -> bool:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                if soft_delete:
                    query = "UPDATE memories SET is_deleted = TRUE, updated_at = ? WHERE id = ? AND is_deleted = FALSE"
                    params = (datetime.now().isoformat(), memory_id)
                else:
                    query = "DELETE FROM memories WHERE id = ?"
                    params = (memory_id,)

                cursor.execute(query, params)

                success = cursor.rowcount > 0

                if success:
                    cursor.execute('''
                        INSERT INTO audit_logs (operation, memory_id, operator, details)
                        VALUES (?, ?, ?, ?)
                    ''', ("delete" if not soft_delete else "soft_delete", memory_id, "system", json_dumps({"soft_delete": soft_delete})))

                conn.commit()
                return success
            finally:
                conn.close()

    def get_statistics(self, workspace_id: str = "default") -> Dict:
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT COUNT(*) FROM memories WHERE is_deleted = FALSE AND workspace_id = ?", (workspace_id,))
            total = cursor.fetchone()[0]

            cursor.execute("SELECT type, COUNT(*) FROM memories WHERE is_deleted = FALSE AND workspace_id = ? GROUP BY type", (workspace_id,))
            by_type = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("SELECT COUNT(*) FROM memories WHERE is_deleted = TRUE AND workspace_id = ?", (workspace_id,))
            soft_deleted = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM memories WHERE permanent = TRUE AND is_deleted = FALSE AND workspace_id = ?", (workspace_id,))
            permanent = cursor.fetchone()[0]

            return {
                "total": total,
                "by_type": by_type,
                "soft_deleted": soft_deleted,
                "permanent": permanent
            }
        finally:
            conn.close()

    def _row_to_memory(self, row) -> Dict:
        try:
            metadata = json_loads(row[4] or "{}")
            tags = json_loads(row[13] or "[]")
            decay_params = json_loads(row[8] or "{}")
        except Exception:
            metadata = {}
            tags = []
            decay_params = {}

        return {
            "id": row[0],
            "type": row[1],
            "content": row[2],
            "vector_id": row[3],
            "metadata": metadata,
            "importance": row[5],
            "importance_score": row[6],
            "decay_type": row[7],
            "decay_params": decay_params,
            "reactivation_count": row[9],
            "emotion_score": row[10],
            "permanent": bool(row[11]),
            "psychological_age": row[12],
            "tags": tags,
            "created_at": row[14],
            "updated_at": row[15],
            "archived_at": row[16],
            "is_deleted": bool(row[17]),
            "source": row[18],
            "workspace_id": row[19]
        }

    def enable_vector_search(
        self,
        embedding_model=None,
        vector_store=None,
        vector_backend: str = "milvus_lite",
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        milvus_db_path: str = "data/milvus_lite.db"
    ):
        if vector_store is None:
            try:
                from backend.core.memory.vector_store import create_vector_store
                dimension = embedding_model.dimension if embedding_model else 768

                if vector_backend == "milvus_lite":
                    vector_store = create_vector_store(
                        backend="milvus_lite",
                        db_path=milvus_db_path,
                        vector_size=dimension,
                        embedding_model=embedding_model
                    )
                elif vector_backend == "qdrant":
                    vector_store = create_vector_store(
                        backend="qdrant",
                        host=qdrant_host,
                        port=qdrant_port,
                        vector_size=dimension,
                        embedding_model=embedding_model
                    )
                else:
                    logger.warning(f"未知的向量存储后端: {vector_backend}")
                    return

                self._vector_store = vector_store
            except ImportError as e:
                logger.warning(f"向量存储未安装，向量功能不可用: {e}")
                return
        else:
            self._vector_store = vector_store

        self._embedding_model = embedding_model

        if self._vector_store and self._embedding_model:
            from backend.core.memory.hybrid_search import HybridSearch
            self._hybrid_search = HybridSearch(
                vector_store=self._vector_store,
                sqlite_manager=self,
                embedding_model=self._embedding_model
            )
            logger.info(f"向量搜索功能已启用 (后端: {vector_backend})")

    def is_vector_search_enabled(self) -> bool:
        with self._lock:
            return self._hybrid_search is not None and self._vector_store is not None

    async def semantic_search(self, query: str, memory_type: str = None, limit: int = 10) -> List[Dict]:
        if not self.is_vector_search_enabled():
            return self.search_memories(query=query, memory_type=memory_type, limit=limit)

        try:
            results = await self._hybrid_search.semantic_search(
                query=query,
                memory_type=memory_type,
                limit=limit
            )
            return results
        except Exception as e:
            logger.error(f"语义搜索失败: {e}")
            return self.search_memories(query=query, memory_type=memory_type, limit=limit)

    async def hybrid_search(self, query: str, memory_type: str = None, tags: List[str] = None, limit: int = 10) -> List[Dict]:
        if not self.is_vector_search_enabled():
            return self.search_memories(query=query, memory_type=memory_type, tags=tags, limit=limit)

        try:
            from backend.core.memory.hybrid_search import HybridSearchOptions
            options = HybridSearchOptions(
                query=query,
                memory_type=memory_type,
                tags=tags,
                limit=limit
            )

            search_results = await self._hybrid_search.search(options)

            return [
                {
                    "memory_id": r.memory_id,
                    "content": r.content,
                    "score": r.score,
                    "source": r.source,
                    "metadata": r.metadata
                }
                for r in search_results
            ]
        except Exception as e:
            logger.error(f"混合搜索失败: {e}")
            return self.search_memories(query=query, memory_type=memory_type, tags=tags, limit=limit)

    def write_permanent_memory(
        self,
        content: str,
        tags: List[str] = None,
        metadata: Dict = None,
        emotion_score: float = 0.0,
        source: str = "user",
        is_from_main: bool = True
    ) -> int:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                cursor.execute('''
                    INSERT INTO permanent_memories (
                        content, importance_score, emotion_score,
                        tags, metadata, created_at, source, verified
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    content,
                    1.0,
                    emotion_score,
                    json_dumps(tags or [], ensure_ascii=False),
                    json_dumps(metadata or {}, ensure_ascii=False),
                    datetime.now().isoformat(),
                    source,
                    is_from_main
                ))

                memory_id = cursor.lastrowid

                cursor.execute('''
                    INSERT INTO audit_logs (operation, memory_id, session_id, operator, details)
                    VALUES (?, ?, ?, ?, ?)
                ''', ("create_permanent", memory_id, None, "main_model" if is_from_main else "secondary_model", json_dumps({"source": source})))

                conn.commit()
                logger.info(f"永久记忆已写入: id={memory_id}, source={source}")
                return memory_id
            finally:
                conn.close()

    def get_permanent_memory(self, memory_id: int) -> Optional[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM permanent_memories WHERE id = ?", (memory_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_permanent_memory(row)
            return None
        finally:
            conn.close()

    def get_permanent_memories(
        self,
        limit: int = 20,
        offset: int = 0,
        tags: List[str] = None
    ) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = "SELECT * FROM permanent_memories WHERE 1=1"
            params = []

            if tags:
                for tag in tags:
                    query += " AND tags LIKE ?"
                    params.append(f'%"{tag}"%')

            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_permanent_memory(row) for row in rows]
        finally:
            conn.close()

    def update_permanent_memory(
        self,
        memory_id: int,
        content: str = None,
        tags: List[str] = None,
        metadata: Dict = None
    ) -> bool:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                updates = []
                params = []

                if content is not None:
                    updates.append("content = ?")
                    params.append(content)

                if tags is not None:
                    updates.append("tags = ?")
                    params.append(json_dumps(tags, ensure_ascii=False))

                if metadata is not None:
                    updates.append("metadata = ?")
                    params.append(json_dumps(metadata, ensure_ascii=False))

                if not updates:
                    return False

                updates.append("updated_at = ?")
                params.append(datetime.now().isoformat())
                params.append(memory_id)

                query = f"UPDATE permanent_memories SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(query, params)

                success = cursor.rowcount > 0

                if success:
                    cursor.execute('''
                        INSERT INTO audit_logs (operation, memory_id, session_id, operator, details)
                        VALUES (?, ?, ?, ?, ?)
                    ''', ("update_permanent", memory_id, None, "system", json_dumps({"updates": updates})))

                conn.commit()
                return success
            finally:
                conn.close()

    def delete_permanent_memory(self, memory_id: int, is_from_main: bool = True) -> bool:
        if not is_from_main:
            logger.warning(f"副模型无权删除永久记忆: id={memory_id}")
            return False

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                cursor.execute("DELETE FROM permanent_memories WHERE id = ?", (memory_id,))

                success = cursor.rowcount > 0

                if success:
                    cursor.execute('''
                        INSERT INTO audit_logs (operation, memory_id, session_id, operator, details)
                        VALUES (?, ?, ?, ?, ?)
                    ''', ("delete_permanent", memory_id, None, "main_model", json_dumps({})))

                conn.commit()
                return success
            finally:
                conn.close()

    def _row_to_permanent_memory(self, row) -> Dict:
        try:
            metadata = json_loads(row[6] or "{}")
            tags = json_loads(row[4] or "[]")
        except Exception:
            metadata = {}
            tags = []

        return {
            "id": row[0],
            "content": row[1],
            "importance_score": row[2],
            "emotion_score": row[3],
            "tags": tags,
            "created_at": row[5],
            "updated_at": row[6],
            "metadata": metadata,
            "source": row[8]
        }

    def search_memories_3d(
        self,
        query: str = None,
        memory_type: str = None,
        tags: List[str] = None,
        limit: int = 10,
        weights: Tuple[float, float, float] = (0.35, 0.25, 0.4),
        workspace_id: str = "default"
    ) -> List[Dict]:
        from backend.core.memory.decay import DecayCalculator

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            conditions = ["workspace_id = ?", "is_deleted = FALSE"]
            params = [workspace_id]

            if query:
                conditions.append("content LIKE ?")
                params.append(f"%{query}%")

            if memory_type:
                conditions.append("type = ?")
                params.append(memory_type)

            if tags:
                for tag in tags:
                    conditions.append("tags LIKE ?")
                    params.append(f'%"{tag}"%')

            where_clause = " AND ".join(conditions)
            params.append(limit * 2)

            cursor.execute(
                f"SELECT * FROM memories WHERE {where_clause} ORDER BY importance DESC, created_at DESC LIMIT ?",
                params
            )

            rows = cursor.fetchall()
        finally:
            conn.close()

        decay_calculator = DecayCalculator()
        scored_memories = []

        for row in rows:
            memory = self._row_to_memory(row)

            importance_score = decay_calculator.calculate_importance_score(memory)
            time_score = decay_calculator.calculate_time_score(memory, apply_reactivation=True)
            relevance_score = memory.get("score", 0.5)

            final_score = (
                importance_score * weights[0] +
                time_score * weights[1] +
                relevance_score * weights[2]
            )

            if memory.get("permanent"):
                final_score = min(final_score + 0.15, 1.0)

            final_score = min(final_score, 1.0)

            memory["final_score"] = final_score
            memory["component_scores"] = {
                "importance": importance_score,
                "time": time_score,
                "relevance": relevance_score
            }
            memory["applied_weights"] = {
                "importance": weights[0],
                "time": weights[1],
                "relevance": weights[2]
            }

            scored_memories.append(memory)

        scored_memories.sort(key=lambda m: m["final_score"], reverse=True)

        return scored_memories[:limit]

    def recall_memory(
        self,
        memory_id: int,
        emotion_intensity: float = 0.0
    ) -> Optional[Dict]:
        from backend.core.memory.decay import DecayCalculator

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                cursor.execute("SELECT * FROM memories WHERE id = ? AND is_deleted = FALSE", (memory_id,))
                row = cursor.fetchone()

                if not row:
                    return None

                memory = self._row_to_memory(row)

                reactivation_count = memory.get("reactivation_count", 0)
                decay_calculator = DecayCalculator()
                old_time_score = decay_calculator.calculate_time_score(memory, apply_reactivation=False)

                new_time_score = min(1.0, old_time_score * (1 + 0.2 * reactivation_count) + 0.1)
                emotion_bonus = 0.05 * abs(emotion_intensity)
                new_time_score = min(new_time_score + emotion_bonus, 1.0)

                new_reactivation_count = reactivation_count + 1
                new_emotion_score = (memory.get("emotion_score", 0.0) + abs(emotion_intensity)) / 2

                cursor.execute('''
                    UPDATE memories
                    SET reactivation_count = ?, emotion_score = ?, updated_at = ?
                    WHERE id = ?
                ''', (new_reactivation_count, new_emotion_score, datetime.now().isoformat(), memory_id))

                cursor.execute('''
                    INSERT INTO audit_logs (operation, memory_id, session_id, operator, details)
                    VALUES (?, ?, ?, ?, ?)
                ''', ("recall", memory_id, None, "system", json_dumps({
                    "reactivation_count": new_reactivation_count,
                    "emotion_intensity": emotion_intensity,
                    "old_time_score": old_time_score,
                    "new_time_score": new_time_score,
                    "memory_type": memory.get("type")
                })))

                conn.commit()

                logger.info(f"记忆已召回: id={memory_id}, reactivation_count={new_reactivation_count}")

                updated_memory = self.get_memory(memory_id)
                if updated_memory:
                    updated_memory["reactivation_details"] = {
                        "old_time_score": old_time_score,
                        "new_time_score": new_time_score,
                        "emotion_bonus": emotion_bonus,
                        "reactivation_count": new_reactivation_count
                    }

                return updated_memory
            finally:
                conn.close()

    def batch_write_memories(
        self,
        memories: List[Dict],
        raise_on_error: bool = False
    ) -> Dict:
        results = {
            "success": 0,
            "failed": 0,
            "errors": [],
            "memory_ids": []
        }

        for mem_data in memories:
            try:
                memory_id = self.write_memory(
                    content=mem_data.get("content", ""),
                    memory_type=mem_data.get("type", "long_term"),
                    importance=mem_data.get("importance", 3),
                    tags=mem_data.get("tags", []),
                    metadata=mem_data.get("metadata", {}),
                    permanent=mem_data.get("permanent", False),
                    emotion_score=mem_data.get("emotion_score", 0.0),
                    workspace_id=mem_data.get("workspace_id", "default")
                )
                results["success"] += 1
                results["memory_ids"].append(memory_id)
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(str(e))
                if raise_on_error:
                    raise

        logger.info(f"批量写入完成: 成功={results['success']}, 失败={results['failed']}")
        return results

    def batch_update_memories(
        self,
        updates: List[Dict],
        raise_on_error: bool = False
    ) -> Dict:
        results = {
            "success": 0,
            "failed": 0,
            "errors": [],
            "updated_ids": []
        }

        for update_data in updates:
            try:
                memory_id = update_data.get("memory_id")
                if not memory_id:
                    raise ValueError("memory_id is required")

                success = self.update_memory(
                    memory_id=memory_id,
                    new_content=update_data.get("content"),
                    new_tags=update_data.get("tags"),
                    new_importance=update_data.get("importance"),
                    new_metadata=update_data.get("metadata")
                )

                if success:
                    results["success"] += 1
                    results["updated_ids"].append(memory_id)
                else:
                    results["failed"] += 1
                    results["errors"].append(f"Memory {memory_id} not found")
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(str(e))
                if raise_on_error:
                    raise

        logger.info(f"批量更新完成: 成功={results['success']}, 失败={results['failed']}")
        return results

    def batch_delete_memories(
        self,
        memory_ids: List[int],
        soft_delete: bool = True,
        raise_on_error: bool = False
    ) -> Dict:
        results = {
            "success": 0,
            "failed": 0,
            "errors": [],
            "deleted_ids": []
        }

        for memory_id in memory_ids:
            try:
                success = self.delete_memory(memory_id, soft_delete=soft_delete)

                if success:
                    results["success"] += 1
                    results["deleted_ids"].append(memory_id)
                else:
                    results["failed"] += 1
                    results["errors"].append(f"Memory {memory_id} not found")
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(str(e))
                if raise_on_error:
                    raise

        logger.info(f"批量删除完成: 成功={results['success']}, 失败={results['failed']}")
        return results

    def sync_decay_values(self, workspace_id: str = "default") -> Dict:
        from backend.core.memory.decay import DecayCalculator

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM memories WHERE is_deleted = FALSE AND workspace_id = ?", (workspace_id,))
        rows = cursor.fetchall()

        decay_calculator = DecayCalculator()
        updated_count = 0
        failed_count = 0

        for row in rows:
            try:
                memory = self._row_to_memory(row)

                if memory.get("permanent"):
                    continue

                time_score = decay_calculator.calculate_time_score(memory, apply_reactivation=True)

                cursor.execute('''
                    UPDATE memories
                    SET importance_score = ?, updated_at = ?
                    WHERE id = ?
                ''', (time_score, datetime.now().isoformat(), memory["id"]))

                updated_count += 1
            except Exception as e:
                logger.warning(f"更新衰减值失败 id={row[0]}: {e}")
                failed_count += 1

        conn.commit()
        conn.close()

        logger.info(f"衰减同步完成: 更新={updated_count}, 失败={failed_count}")

        return {
            "updated": updated_count,
            "failed": failed_count,
            "total": len(rows)
        }

    def get_decay_statistics(self, workspace_id: str = "default") -> Dict:
        from backend.core.memory.decay import DecayCalculator

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM memories WHERE is_deleted = FALSE AND workspace_id = ?", (workspace_id,))
        total = cursor.fetchone()[0]

        cursor.execute('''
            SELECT importance_score, COUNT(*)
            FROM memories
            WHERE is_deleted = FALSE AND workspace_id = ?
            GROUP BY importance_score
        ''', (workspace_id,))
        distribution = {row[0]: row[1] for row in cursor.fetchall()}

        decay_calculator = DecayCalculator()

        cursor.execute("SELECT * FROM memories WHERE is_deleted = FALSE AND workspace_id = ?", (workspace_id,))
        rows = cursor.fetchall()

        avg_time_score = 0.0
        avg_importance_score = 0.0
        reactivation_stats = {"total": 0, "avg_count": 0.0}

        for row in rows:
            memory = self._row_to_memory(row)

            if not memory.get("permanent"):
                time_score = decay_calculator.calculate_time_score(memory, apply_reactivation=True)
                avg_time_score += time_score

            avg_importance_score += memory.get("importance_score", 0.0)

            reactivation_count = memory.get("reactivation_count", 0)
            if reactivation_count > 0:
                reactivation_stats["total"] += 1
                reactivation_stats["avg_count"] += reactivation_count

        non_permanent_count = total - sum(1 for row in rows if self._row_to_memory(row).get("permanent"))

        if non_permanent_count > 0:
            avg_time_score /= non_permanent_count

        if total > 0:
            avg_importance_score /= total

        if reactivation_stats["total"] > 0:
            reactivation_stats["avg_count"] /= reactivation_stats["total"]

        conn.close()

        return {
            "total_memories": total,
            "non_permanent_count": non_permanent_count,
            "permanent_count": total - non_permanent_count,
            "avg_time_score": round(avg_time_score, 4),
            "avg_importance_score": round(avg_importance_score, 4),
            "importance_distribution": distribution,
            "reactivation_stats": {
                "reactivated_count": reactivation_stats["total"],
                "avg_reactivation_count": round(reactivation_stats["avg_count"], 2)
            }
        }

        