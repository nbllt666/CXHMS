import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import yaml


class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    VLLM = "vllm"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    LOCAL = "local"


class MemoryType(str, Enum):
    PERMANENT = "permanent"
    LONG_TERM = "long_term"
    SHORT_TERM = "short_term"


class AgentStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"


class MessageType(str, Enum):
    CHAT = "chat"
    MEMORY_REQUEST = "memory_request"
    MEMORY_RESPONSE = "memory_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    BROADCAST = "broadcast"
    GROUP_MESSAGE = "group_message"
    SYNC = "sync"
    CONTROL = "control"


@dataclass
class LLMConfig:
    provider: str = "ollama"
    host: str = "http://localhost:11434"
    model: str = "llama3.2"
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = True
    api_key: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMConfig":
        return cls(
            provider=data.get("provider", "ollama"),
            host=data.get("host", "http://localhost:11434"),
            model=data.get("model", "llama3.2"),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 4096),
            stream=data.get("stream", True),
            api_key=data.get("api_key")
        )


@dataclass
class VectorConfig:
    enabled: bool = True
    host: str = "localhost"
    port: int = 6333
    collection_name: str = "cxhms_memories"
    embedding_model: str = "nomic-embed-text"
    embedding_dimension: int = 768
    api_key: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VectorConfig":
        return cls(
            enabled=data.get("enabled", True),
            host=data.get("host", "localhost"),
            port=data.get("port", 6333),
            collection_name=data.get("collection_name", "cxhms_memories"),
            embedding_model=data.get("embedding_model", "nomic-embed-text"),
            embedding_dimension=data.get("embedding_dimension", 768),
            api_key=data.get("api_key")
        )


@dataclass
class ACPDiscoveryConfig:
    enabled: bool = True
    port: int = 9999
    broadcast_port: int = 9998
    broadcast_address: str = "255.255.255.255"
    interval: int = 30

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPDiscoveryConfig":
        return cls(
            enabled=data.get("enabled", True),
            port=data.get("port", 9999),
            broadcast_port=data.get("broadcast_port", 9998),
            broadcast_address=data.get("broadcast_address", "255.255.255.255"),
            interval=data.get("interval", 30)
        )


@dataclass
class ACPConnectionConfig:
    port: int = 10000
    heartbeat_interval: int = 10
    timeout: int = 30

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPConnectionConfig":
        return cls(
            port=data.get("port", 10000),
            heartbeat_interval=data.get("heartbeat_interval", 10),
            timeout=data.get("timeout", 30)
        )


@dataclass
class ACPGroupConfig:
    port: int = 10001
    max_members: int = 50

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPGroupConfig":
        return cls(
            port=data.get("port", 10001),
            max_members=data.get("max_members", 50)
        )


@dataclass
class ACPConfig:
    enabled: bool = True
    agent_id: str = "cxhms-agent-001"
    agent_name: str = "CXHMS Agent"
    discovery: ACPDiscoveryConfig = field(default_factory=ACPDiscoveryConfig)
    connection: ACPConnectionConfig = field(default_factory=ACPConnectionConfig)
    group: ACPGroupConfig = field(default_factory=ACPGroupConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPConfig":
        return cls(
            enabled=data.get("enabled", True),
            agent_id=data.get("agent_id", "cxhms-agent-001"),
            agent_name=data.get("agent_name", "CXHMS Agent"),
            discovery=ACPDiscoveryConfig.from_dict(data.get("discovery", {})),
            connection=ACPConnectionConfig.from_dict(data.get("connection", {})),
            group=ACPGroupConfig.from_dict(data.get("group", {}))
        )


@dataclass
class DatabaseConfig:
    path: str = "data/memories.db"
    pool_size: int = 10
    max_overflow: int = 20

    @property
    def url(self) -> str:
        return f"sqlite+aiosqlite:///{self.path}"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DatabaseConfig":
        return cls(
            path=data.get("path", "data/memories.db"),
            pool_size=data.get("pool_size", 10),
            max_overflow=data.get("max_overflow", 20)
        )


@dataclass
class MilvusLiteConfig:
    db_path: str = "data/milvus_lite.db"
    vector_size: int = 768

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MilvusLiteConfig":
        return cls(
            db_path=data.get("db_path", "data/milvus_lite.db"),
            vector_size=data.get("vector_size", 768)
        )


@dataclass
class QdrantConfig:
    host: str = "localhost"
    port: int = 6333
    vector_size: int = 768

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QdrantConfig":
        return cls(
            host=data.get("host", "localhost"),
            port=data.get("port", 6333),
            vector_size=data.get("vector_size", 768)
        )


@dataclass
class MemoryConfig:
    decay_enabled: bool = True
    batch_interval: int = 3600
    permanent_threshold: float = 0.95
    max_short_term_age_days: int = 7
    max_long_term_age_days: int = 365
    vector_enabled: bool = True
    vector_backend: str = "milvus_lite"
    milvus_lite: MilvusLiteConfig = field(default_factory=MilvusLiteConfig)
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryConfig":
        return cls(
            decay_enabled=data.get("decay_enabled", True),
            batch_interval=data.get("batch_interval", 3600),
            permanent_threshold=data.get("permanent_threshold", 0.95),
            max_short_term_age_days=data.get("max_short_term_age_days", 7),
            max_long_term_age_days=data.get("max_long_term_age_days", 365),
            vector_enabled=data.get("vector_enabled", True),
            vector_backend=data.get("vector_backend", "milvus_lite"),
            milvus_lite=MilvusLiteConfig.from_dict(data.get("milvus_lite", {})),
            qdrant=QdrantConfig.from_dict(data.get("qdrant", {}))
        )


@dataclass
class ContextConfig:
    max_messages: int = 100
    summary_threshold: int = 20
    window_size: int = 10
    enable_summary: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextConfig":
        return cls(
            max_messages=data.get("max_messages", 100),
            summary_threshold=data.get("summary_threshold", 20),
            window_size=data.get("window_size", 10),
            enable_summary=data.get("enable_summary", True)
        )


@dataclass
class RateLimitConfig:
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RateLimitConfig":
        return cls(
            enabled=data.get("enabled", True)
        )


@dataclass
class CORSConfig:
    enabled: bool = True
    origins: List[str] = field(default_factory=lambda: ["*"])
    allow_credentials: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CORSConfig":
        return cls(
            enabled=data.get("enabled", True),
            origins=data.get("origins", ["*"]),
            allow_credentials=data.get("allow_credentials", True)
        )


@dataclass
class SystemConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    workers: int = 1

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystemConfig":
        return cls(
            host=data.get("host", "0.0.0.0"),
            port=data.get("port", 8000),
            debug=data.get("debug", False),
            log_level=data.get("log_level", "INFO"),
            workers=data.get("workers", 1)
        )


@dataclass
class CXHMSConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    vector: VectorConfig = field(default_factory=VectorConfig)
    acp: ACPConfig = field(default_factory=ACPConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    cors: CORSConfig = field(default_factory=CORSConfig)
    system: SystemConfig = field(default_factory=SystemConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CXHMSConfig":
        return cls(
            llm=LLMConfig.from_dict(data.get("llm", {})),
            vector=VectorConfig.from_dict(data.get("vector", {})),
            acp=ACPConfig.from_dict(data.get("acp", {})),
            database=DatabaseConfig.from_dict(data.get("database", {})),
            memory=MemoryConfig.from_dict(data.get("memory", {})),
            context=ContextConfig.from_dict(data.get("context", {})),
            rate_limit=RateLimitConfig.from_dict(data.get("rate_limit", {})),
            cors=CORSConfig.from_dict(data.get("cors", {})),
            system=SystemConfig.from_dict(data.get("system", {}))
        )


class Settings:
    _instance: Optional["Settings"] = None
    _config: Optional[CXHMSConfig] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self._config = self.load_config()

    @property
    def config(self) -> CXHMSConfig:
        return self._config

    def load_config(self, config_path: Optional[str] = None) -> CXHMSConfig:
        if config_path is None:
            config_path = os.getenv("CXHMS_CONFIG_PATH", "config/default.yaml")

        config_file = Path(config_path)

        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return CXHMSConfig.from_dict(data)
        else:
            return CXHMSConfig()

    def reload_config(self, config_path: Optional[str] = None):
        self._config = self.load_config(config_path)

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            elif hasattr(value, k):
                value = getattr(value, k)
            else:
                return default
        return value

    def set(self, key: str, value: Any):
        keys = key.split(".")
        target = self._config
        for k in keys[:-1]:
            if isinstance(target, dict):
                target = target.get(k)
            elif hasattr(target, k):
                target = getattr(target, k)

        final_key = keys[-1]
        if isinstance(target, dict):
            target[final_key] = value
        elif hasattr(target, final_key):
            setattr(target, final_key, value)

    def save_config(self, config_path: str = "config/default.yaml"):
        config_dict = self._config_to_dict(self._config)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_dict, f, allow_unicode=True, indent=2)

    def _config_to_dict(self, config: Any) -> Dict[str, Any]:
        if isinstance(config, dict):
            return {k: self._config_to_dict(v) for k, v in config.items()}
        elif hasattr(config, "__dict__"):
            return {k: self._config_to_dict(v) for k, v in config.__dict__.items() if not k.startswith("_")}
        elif isinstance(config, (list, tuple)):
            return [self._config_to_dict(item) for item in config]
        else:
            return config


settings = Settings()
