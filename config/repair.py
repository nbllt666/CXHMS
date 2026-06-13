"""
配置自动修复模块
根据验证结果自动修复配置问题：缺失字段补默认值、类型错误修正、无效值回退、范围越界裁剪
"""

import copy
import logging
from typing import Any, Dict, List, Tuple

from .validation import ConfigValidator, ValidationResult

logger = logging.getLogger(__name__)


class ConfigRepair:
    """配置自动修复器"""

    # 完整默认值表：从 default.yaml 和各 dataclass 的 from_dict 默认值中提取
    DEFAULTS: Dict[str, Any] = {
        # server
        "server.host": "0.0.0.0",
        "server.port": 8000,
        "server.debug": False,
        # cors
        "cors.enabled": True,
        "cors.origins": ["*"],
        "cors.allow_credentials": True,
        # logging
        "logging.level": "INFO",
        "logging.format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "logging.file": "logs/app.log",
        "logging.max_bytes": 10485760,
        "logging.backup_count": 5,
        # database
        "database.type": "sqlite",
        "database.path": "data/cxhms.db",
        "database.memories_db": "data/memories.db",
        "database.sessions_db": "data/sessions.db",
        "database.acp_db": "data/acp",
        "database.echo": False,
        # models.main
        "models.main.provider": "ollama",
        "models.main.host": "http://localhost:11434",
        "models.main.model": "qwen3-vl:8b",
        "models.main.port": 8000,
        "models.main.temperature": 0.7,
        "models.main.max_tokens": 0,
        "models.main.timeout": 60,
        "models.main.enabled": True,
        # models.summary
        "models.summary.provider": "ollama",
        "models.summary.host": "http://localhost:11434",
        "models.summary.model": "qwen3-vl:8b",
        "models.summary.port": 8000,
        "models.summary.temperature": 0.7,
        "models.summary.max_tokens": 131072,
        "models.summary.timeout": 60,
        "models.summary.enabled": False,
        # models.memory
        "models.memory.provider": "ollama",
        "models.memory.host": "http://localhost:11434",
        "models.memory.model": "qwen3-vl:8b",
        "models.memory.port": 8000,
        "models.memory.temperature": 0.7,
        "models.memory.max_tokens": 4096,
        "models.memory.timeout": 60,
        "models.memory.enabled": False,
        # models.embedding
        "models.embedding.provider": "vllm",
        "models.embedding.host": "http://localhost:8101",
        "models.embedding.model": "Qwen/Qwen3-VL-Embedding-2B",
        "models.embedding.port": 8101,
        "models.embedding.temperature": 0.0,
        "models.embedding.max_tokens": 512,
        "models.embedding.timeout": 60,
        "models.embedding.enabled": True,
        # model_defaults
        "model_defaults.summary": "main",
        "model_defaults.memory": "main",
        # agent
        "agent.agent_id": "cxhms_agent_001",
        "agent.name": "CXHMS Agent",
        "agent.version": "1.0.0",
        # memory
        "memory.enabled": True,
        "memory.max_memories": 10000,
        "memory.default_importance": 3,
        "memory.decay_enabled": True,
        "memory.decay_rate": 0.1,
        "memory.decay_interval_days": 7,
        "memory.reactivation_boost": 0.2,
        "memory.emotion_enabled": True,
        "memory.vector_enabled": True,
        "memory.vector_backend": "weaviate",
        "memory.decay_model": "exponential",
        "memory.hybrid_search_enabled": False,
        "memory.archive_enabled": True,
        "memory.dedup_threshold": 0.85,
        "memory.archive_compression_enabled": True,
        # memory.chroma
        "memory.chroma.db_path": "data/chroma_db",
        "memory.chroma.collection_name": "memory_vectors",
        "memory.chroma.vector_size": 768,
        # memory.milvus_lite
        "memory.milvus_lite.db_path": "data/milvus_lite.db",
        "memory.milvus_lite.vector_size": 768,
        # memory.qdrant
        "memory.qdrant.host": "localhost",
        "memory.qdrant.port": 6333,
        "memory.qdrant.vector_size": 768,
        # memory.weaviate
        "memory.weaviate.host": "localhost",
        "memory.weaviate.port": 8090,
        "memory.weaviate.grpc_port": 50061,
        "memory.weaviate.embedded": False,
        "memory.weaviate.vector_size": 768,
        "memory.weaviate.schema_class": "CXHMSMemory",
        # context
        "context.enabled": True,
        "context.max_context_length": 4000,
        "context.context_window": 10,
        "context.include_memories": True,
        "context.max_memories_in_context": 5,
        # tools
        "tools.enabled": True,
        "tools.auto_discovery": True,
        "tools.mcp_enabled": False,
        # acp
        "acp.enabled": True,
        "acp.local_agent_id": "cxhms_agent_001",
        "acp.local_agent_name": "CXHMS Agent",
        "acp.discovery_enabled": True,
        "acp.discovery_port": 9999,
        "acp.broadcast_port": 9998,
        "acp.broadcast_address": "255.255.255.255",
        "acp.discovery_interval": 30,
        # security
        "security.api_key_enabled": False,
        "security.api_key": "",
        "security.rate_limit_enabled": False,
        "security.rate_limit_requests": 100,
        "security.rate_limit_period": 60,
        # monitoring
        "monitoring.enabled": True,
        "monitoring.metrics_enabled": True,
        "monitoring.health_check_enabled": True,
        "monitoring.performance_logging": True,
        # llm_params
        "llm_params.temperature": 1.3,
        "llm_params.maxTokens": 0,
        "llm_params.topP": 0.9,
        "llm_params.timeout": 30,
    }

    # 类型映射：用于类型错误修正
    TYPE_MAP: Dict[str, type] = {
        "server.port": int,
        "server.debug": bool,
        "models.main.port": int,
        "models.main.temperature": float,
        "models.main.max_tokens": int,
        "models.main.timeout": int,
        "models.main.enabled": bool,
        "models.summary.port": int,
        "models.summary.temperature": float,
        "models.summary.max_tokens": int,
        "models.summary.timeout": int,
        "models.summary.enabled": bool,
        "models.memory.port": int,
        "models.memory.temperature": float,
        "models.memory.max_tokens": int,
        "models.memory.timeout": int,
        "models.memory.enabled": bool,
        "memory.max_memories": int,
        "memory.default_importance": int,
        "memory.decay_enabled": bool,
        "memory.decay_rate": float,
        "memory.decay_interval_days": int,
        "memory.reactivation_boost": float,
        "memory.emotion_enabled": bool,
        "memory.vector_enabled": bool,
        "memory.hybrid_search_enabled": bool,
        "memory.archive_enabled": bool,
        "memory.dedup_threshold": float,
        "memory.archive_compression_enabled": bool,
        "memory.chroma.vector_size": int,
        "memory.milvus_lite.vector_size": int,
        "memory.qdrant.port": int,
        "memory.qdrant.vector_size": int,
        "memory.weaviate.port": int,
        "memory.weaviate.grpc_port": int,
        "memory.weaviate.embedded": bool,
        "memory.weaviate.vector_size": int,
        "context.max_context_length": int,
        "context.context_window": int,
        "context.include_memories": bool,
        "context.max_memories_in_context": int,
        "tools.enabled": bool,
        "tools.auto_discovery": bool,
        "tools.mcp_enabled": bool,
        "acp.enabled": bool,
        "acp.discovery_enabled": bool,
        "acp.discovery_port": int,
        "acp.broadcast_port": int,
        "acp.discovery_interval": int,
        "security.api_key_enabled": bool,
        "security.rate_limit_enabled": bool,
        "security.rate_limit_requests": int,
        "security.rate_limit_period": int,
        "monitoring.enabled": bool,
        "monitoring.metrics_enabled": bool,
        "monitoring.health_check_enabled": bool,
        "monitoring.performance_logging": bool,
        "logging.max_bytes": int,
        "logging.backup_count": int,
        "llm_params.temperature": float,
        "llm_params.maxTokens": int,
        "llm_params.topP": float,
        "llm_params.timeout": int,
    }

    @classmethod
    def repair(
        cls, config_dict: Dict[str, Any], validation_result: ValidationResult
    ) -> Tuple[Dict[str, Any], List[str]]:
        """根据验证结果自动修复配置

        Args:
            config_dict: 原始配置字典
            validation_result: 验证结果

        Returns:
            (修复后配置, 修复记录列表)
        """
        repairs = []
        repaired = copy.deepcopy(config_dict)

        # 1. 补全缺失的必填字段
        repairs.extend(cls._repair_missing_fields(repaired, validation_result))

        # 2. 修正类型错误
        repairs.extend(cls._repair_type_errors(repaired, validation_result))

        # 3. 回退无效值到默认值
        repairs.extend(cls._repair_invalid_values(repaired, validation_result))

        # 4. 裁剪越界值到合法范围
        repairs.extend(cls._repair_range_violations(repaired, validation_result))

        # 5. 补全依赖缺失
        repairs.extend(cls._repair_dependencies(repaired, validation_result))

        return repaired, repairs

    @classmethod
    def _get_nested_value(cls, config: Dict, path: str) -> Tuple[bool, Any]:
        """获取嵌套字典值"""
        keys = path.split(".")
        current = config
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return False, None
            current = current[key]
        return True, current

    @classmethod
    def _set_nested_value(cls, config: Dict, path: str, value: Any) -> None:
        """设置嵌套字典值"""
        keys = path.split(".")
        current = config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value

    @classmethod
    def _repair_missing_fields(
        cls, config: Dict, validation_result: ValidationResult
    ) -> List[str]:
        """补全缺失的必填字段"""
        repairs = []

        for error in validation_result.errors:
            if "必填字段缺失" in error.message:
                field_path = error.field
                if field_path in cls.DEFAULTS:
                    default_value = cls.DEFAULTS[field_path]
                    cls._set_nested_value(config, field_path, default_value)
                    repairs.append(f"补全缺失字段 {field_path} = {default_value}")
                else:
                    logger.warning(f"缺失字段 {field_path} 无默认值，无法自动修复")

        return repairs

    @classmethod
    def _repair_type_errors(
        cls, config: Dict, validation_result: ValidationResult
    ) -> List[str]:
        """修正类型错误"""
        repairs = []

        for error in validation_result.errors:
            if "类型错误" in error.message:
                field_path = error.field
                exists, current_value = cls._get_nested_value(config, field_path)

                if not exists or current_value is None:
                    continue

                target_type = cls.TYPE_MAP.get(field_path)
                if target_type is None:
                    # 从 REQUIRED_FIELDS 获取期望类型
                    target_type = ConfigValidator.REQUIRED_FIELDS.get(field_path)

                if target_type is None:
                    continue

                # 尝试类型转换
                converted = cls._try_convert(current_value, target_type)
                if converted is not None:
                    cls._set_nested_value(config, field_path, converted)
                    repairs.append(
                        f"修正类型 {field_path}: {current_value!r} ({type(current_value).__name__}) -> {converted!r} ({target_type.__name__})"
                    )
                else:
                    # 转换失败，使用默认值
                    if field_path in cls.DEFAULTS:
                        default = cls.DEFAULTS[field_path]
                        cls._set_nested_value(config, field_path, default)
                        repairs.append(
                            f"类型转换失败，使用默认值 {field_path}: {current_value!r} -> {default!r}"
                        )

        return repairs

    @classmethod
    def _repair_invalid_values(
        cls, config: Dict, validation_result: ValidationResult
    ) -> List[str]:
        """回退无效值到默认值"""
        repairs = []

        for error in validation_result.errors:
            if "无效值" in error.message:
                field_path = error.field
                if field_path in cls.DEFAULTS:
                    default_value = cls.DEFAULTS[field_path]
                    exists, current_value = cls._get_nested_value(config, field_path)
                    cls._set_nested_value(config, field_path, default_value)
                    repairs.append(
                        f"回退无效值 {field_path}: {current_value!r} -> {default_value!r}"
                    )

        return repairs

    @classmethod
    def _repair_range_violations(
        cls, config: Dict, validation_result: ValidationResult
    ) -> List[str]:
        """裁剪越界值到合法范围"""
        repairs = []

        for error in validation_result.errors:
            if "值超出范围" in error.message:
                field_path = error.field
                range_constraint = ConfigValidator.RANGE_CONSTRAINTS.get(field_path)

                if range_constraint is None:
                    continue

                min_val, max_val = range_constraint
                exists, current_value = cls._get_nested_value(config, field_path)

                if not exists or current_value is None:
                    continue

                try:
                    num_value = float(current_value)
                    if num_value < min_val:
                        # 裁剪到最小值
                        clamped = type(current_value)(min_val) if not isinstance(
                            current_value, float
                        ) else min_val
                        cls._set_nested_value(config, field_path, clamped)
                        repairs.append(
                            f"裁剪越界值 {field_path}: {current_value} -> {clamped} (最小值: {min_val})"
                        )
                    elif num_value > max_val:
                        # 裁剪到最大值
                        clamped = type(current_value)(max_val) if not isinstance(
                            current_value, float
                        ) else max_val
                        cls._set_nested_value(config, field_path, clamped)
                        repairs.append(
                            f"裁剪越界值 {field_path}: {current_value} -> {clamped} (最大值: {max_val})"
                        )
                except (ValueError, TypeError):
                    pass

        return repairs

    @classmethod
    def _repair_dependencies(
        cls, config: Dict, validation_result: ValidationResult
    ) -> List[str]:
        """补全依赖缺失"""
        repairs = []

        for error in validation_result.errors:
            # Qdrant 后端需要 host 和 port
            if "Qdrant后端需要配置" in error.message:
                exists_host, host = cls._get_nested_value(config, "memory.qdrant.host")
                exists_port, port = cls._get_nested_value(config, "memory.qdrant.port")

                if not exists_host or not host:
                    cls._set_nested_value(config, "memory.qdrant.host", "localhost")
                    repairs.append("补全 Qdrant host = localhost")
                if not exists_port or not port:
                    cls._set_nested_value(config, "memory.qdrant.port", 6333)
                    repairs.append("补全 Qdrant port = 6333")

            # Weaviate 后端需要 host
            elif "Weaviate后端需要配置" in error.message:
                exists_host, host = cls._get_nested_value(config, "memory.weaviate.host")
                if not exists_host or not host:
                    cls._set_nested_value(config, "memory.weaviate.host", "localhost")
                    repairs.append("补全 Weaviate host = localhost")

            # API Key 认证需要 api_key
            elif "启用API密钥认证时必须设置" in error.message:
                # 这个无法自动修复（不能生成随机密钥），仅记录警告
                logger.warning("启用 API Key 认证但未设置 api_key，建议手动配置")

        return repairs

    @classmethod
    def _try_convert(cls, value: Any, target_type: type) -> Any:
        """尝试将值转换为目标类型

        Returns:
            转换后的值，转换失败返回 None
        """
        try:
            if target_type == bool:
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes", "on")
                return bool(value)
            elif target_type == int:
                if isinstance(value, bool):
                    return int(value)
                return int(value)
            elif target_type == float:
                if isinstance(value, bool):
                    return float(value)
                return float(value)
            elif target_type == str:
                return str(value)
            else:
                return target_type(value)
        except (ValueError, TypeError):
            return None


def repair_config(
    config_dict: Dict[str, Any], validation_result: ValidationResult
) -> Tuple[Dict[str, Any], List[str]]:
    """配置自动修复便捷函数"""
    return ConfigRepair.repair(config_dict, validation_result)
