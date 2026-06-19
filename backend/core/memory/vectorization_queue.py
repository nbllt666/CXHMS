"""
异步向量化队列 - 将记忆向量化操作改为异步处理

解决记忆创建阻塞问题，提高响应速度
"""
import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from queue import Empty, PriorityQueue
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class VectorizationTask:
    memory_id: str
    content: str
    priority: int = 5
    created_at: datetime = field(default_factory=datetime.now)
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    completed_at: Optional[datetime] = None
    
    def __lt__(self, other):
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.created_at < other.created_at


class VectorizationQueue:
    """向量化任务队列"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, max_workers: int = 2, batch_size: int = 5):
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        self.max_workers = max_workers
        self.batch_size = batch_size
        
        self._queue = PriorityQueue()
        
        self._task_status: Dict[str, VectorizationTask] = {}
        self._status_lock = threading.Lock()
        
        self._workers: List[threading.Thread] = []
        self._stop_event = threading.Event()
        
        self._on_complete_callback: Optional[Callable] = None
        self._on_error_callback: Optional[Callable] = None
        
        self._stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "pending_tasks": 0,
            "processing_tasks": 0,
        }
        self._stats_lock = threading.Lock()
        
        self._initialized = True
        logger.info(f"VectorizationQueue initialized (workers={max_workers}, batch_size={batch_size})")
    
    @classmethod
    def get_instance(cls) -> "VectorizationQueue":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def start(self):
        if self._workers:
            logger.warning("Workers already started")
            return
        
        logger.info(f"Starting {self.max_workers} worker threads")
        for i in range(self.max_workers):
            worker = threading.Thread(target=self._worker_loop, name=f"VectorizationWorker-{i}", daemon=True)
            worker.start()
            self._workers.append(worker)
        
        logger.info("All workers started")
    
    def stop(self):
        logger.info("Stopping workers...")
        self._stop_event.set()
        
        for worker in self._workers:
            worker.join(timeout=5.0)
        
        self._workers.clear()
        logger.info("All workers stopped")
    
    def set_callbacks(self, on_complete: Callable, on_error: Callable):
        self._on_complete_callback = on_complete
        self._on_error_callback = on_error
    
    def add_task(self, memory_id: str, content: str, priority: int = 5) -> str:
        task = VectorizationTask(
            memory_id=memory_id,
            content=content,
            priority=priority
        )
        
        with self._status_lock:
            self._task_status[memory_id] = task
        with self._stats_lock:
            self._stats["total_tasks"] += 1
            self._stats["pending_tasks"] += 1
        
        self._queue.put(task)
        logger.debug(f"Added vectorization task: {memory_id} (priority={priority})")
        
        return memory_id
    
    def get_task_status(self, memory_id: str) -> Optional[Dict]:
        with self._status_lock:
            task = self._task_status.get(memory_id)
            if not task:
                return None
            
            return {
                "memory_id": task.memory_id,
                "status": task.status.value,
                "priority": task.priority,
                "retry_count": task.retry_count,
                "error_message": task.error_message,
                "created_at": task.created_at.isoformat(),
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
    
    def get_stats(self) -> Dict:
        with self._stats_lock:
            return self._stats.copy()
    
    def _worker_loop(self):
        logger.debug(f"Worker {threading.current_thread().name} started")
        
        while not self._stop_event.is_set():
            try:
                try:
                    task = self._queue.get(timeout=1.0)
                except Empty:
                    continue
                
                self._update_task_status(task.memory_id, TaskStatus.PROCESSING)
                with self._stats_lock:
                    self._stats["processing_tasks"] += 1
                    self._stats["pending_tasks"] -= 1

                try:
                    if self._on_complete_callback:
                        self._on_complete_callback(task.memory_id, task.content)
                    
                    task.completed_at = datetime.now()
                    self._update_task_status(task.memory_id, TaskStatus.COMPLETED)
                    
                    with self._stats_lock:
                        self._stats["completed_tasks"] += 1
                        self._stats["processing_tasks"] -= 1
                    
                    logger.debug(f"Vectorization completed: {task.memory_id}")
                    
                except Exception as e:
                    task.retry_count += 1
                    task.error_message = str(e)
                    
                    if task.retry_count < task.max_retries:
                        logger.warning(f"Vectorization failed, retrying ({task.retry_count}/{task.max_retries}): {task.memory_id}")
                        task.status = TaskStatus.PENDING
                        self._queue.put(task)
                        with self._stats_lock:
                            self._stats["processing_tasks"] -= 1
                            self._stats["pending_tasks"] += 1
                    else:
                        logger.error(f"Vectorization failed after {task.max_retries} retries: {task.memory_id}")
                        self._update_task_status(task.memory_id, TaskStatus.FAILED)
                        
                        if self._on_error_callback:
                            self._on_error_callback(task.memory_id, e)
                        
                        with self._stats_lock:
                            self._stats["failed_tasks"] += 1
                            self._stats["processing_tasks"] -= 1
                
                self._queue.task_done()
                
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
        
        logger.debug(f"Worker {threading.current_thread().name} stopped")
    
    def _update_task_status(self, memory_id: str, status: TaskStatus):
        with self._status_lock:
            if memory_id in self._task_status:
                self._task_status[memory_id].status = status


_vectorization_queue = None


def get_vectorization_queue() -> VectorizationQueue:
    global _vectorization_queue
    if _vectorization_queue is None:
        _vectorization_queue = VectorizationQueue()
    return _vectorization_queue


def init_vectorization_queue(max_workers: int = 2, batch_size: int = 5):
    global _vectorization_queue
    _vectorization_queue = VectorizationQueue(max_workers=max_workers, batch_size=batch_size)
    return _vectorization_queue
