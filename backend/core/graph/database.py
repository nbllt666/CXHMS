"""
SQLite 数据库连接管理
"""

import sqlite3
import threading
import logging
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager

from backend.core.graph.config import GraphConfig, get_graph_config

logger = logging.getLogger(__name__)


class Database:
    """SQLite 数据库连接管理器"""

    _local = threading.local()

    def __init__(self, config: GraphConfig = None):
        self.config = config or get_graph_config()
        self.db_path = self.config.database_path
        self.timeout = self.config.timeout
        self._lock = threading.Lock()
        self._init_lock = threading.Lock()

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=self.timeout,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
        return self._local.connection

    @contextmanager
    def get_cursor(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            cursor.close()

    def initialize(self) -> None:
        with self._init_lock:
            self._create_tables()

    def _create_tables(self) -> None:
        with self.get_cursor() as cursor:
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    properties TEXT NOT NULL DEFAULT '{}',
                    text_content TEXT,
                    vector_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
                CREATE INDEX IF NOT EXISTS idx_nodes_created_at ON nodes(created_at);

                CREATE TABLE IF NOT EXISTS edges (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    properties TEXT NOT NULL DEFAULT '{}',
                    text_content TEXT,
                    vector_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (source_id) REFERENCES nodes(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES nodes(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
                CREATE INDEX IF NOT EXISTS idx_edges_relation_type ON edges(relation_type);

                CREATE TABLE IF NOT EXISTS traversal_paths (
                    path_id TEXT PRIMARY KEY,
                    node_ids TEXT NOT NULL,
                    edge_ids TEXT,
                    depth INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            logger.info("图数据库表结构创建完成")

    def health_check(self) -> bool:
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"数据库健康检查失败: {e}")
            return False

    def close(self) -> None:
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
            except Exception as e:
                logger.warning(f"关闭数据库连接失败: {e}")
            finally:
                self._local.connection = None

    def execute(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def execute_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        results = self.execute(query, params)
        return results[0] if results else None

    def execute_modify(self, query: str, params: tuple = ()) -> int:
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount

    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        with self.get_cursor() as cursor:
            cursor.executemany(query, params_list)
            return cursor.rowcount

    def transaction(self, operations: List[Tuple[str, tuple]]) -> None:
        with self.get_cursor() as cursor:
            for query, params in operations:
                cursor.execute(query, params)


_db_instance: Optional[Database] = None


def get_database(config: GraphConfig = None) -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(config)
    return _db_instance
