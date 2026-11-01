"""模块11 独立知识库异常契约测试。

对应 spec「冻结异常契约」表与 public/schema/knowledge.json::definitions.error_codes。
断言 7 个异常：
1. 全部继承 backend.core.exceptions.CXHMSException；
2. error_code / http_status 与契约表逐项一致；
3. 构造后 message / details 可正常透传（details 缺省为 {}）。

运行方式：
    python -m pytest tests/units/test_knowledge_exceptions.py -q
"""

import pytest

from backend.core.exceptions import CXHMSException
from backend.core.knowledge.exceptions import (
    KnowledgeASRUnavailableError,
    KnowledgeError,
    KnowledgeFFmpegUnavailableError,
    KnowledgeParseError,
    KnowledgeStoreError,
    KnowledgeUnsupportedMediaError,
    KnowledgeValidationError,
)

EXPECTED = [
    (KnowledgeError, "KNOWLEDGE_ERROR", 500),
    (KnowledgeValidationError, "KNOWLEDGE_VALIDATION_ERROR", 400),
    (KnowledgeParseError, "KNOWLEDGE_PARSE_FAILED", 500),
    (KnowledgeUnsupportedMediaError, "KNOWLEDGE_UNSUPPORTED_MIME", 415),
    (KnowledgeStoreError, "KNOWLEDGE_STORE_UNAVAILABLE", 503),
    (KnowledgeASRUnavailableError, "KNOWLEDGE_ASR_UNAVAILABLE", 503),
    (KnowledgeFFmpegUnavailableError, "KNOWLEDGE_FFMPEG_UNAVAILABLE", 503),
]


@pytest.mark.parametrize(("exception_class", "error_code", "http_status"), EXPECTED)
def test_exception_inherits_cxhms_exception(exception_class, error_code, http_status):
    """7 个异常均继承 CXHMSException，且 error_code / http_status 与契约一致。"""
    assert issubclass(exception_class, CXHMSException)
    instance = exception_class("测试错误")
    assert instance.error_code == error_code
    assert instance.http_status == http_status
    assert instance.status_code == http_status
    assert instance.message == "测试错误"
    assert instance.details == {}
    assert str(instance) == "测试错误"


@pytest.mark.parametrize(("exception_class", "error_code", "http_status"), EXPECTED)
def test_exception_details_passthrough(exception_class, error_code, http_status):
    """details 参数可透传，且不改变错误码与 HTTP 状态码。"""
    payload = {"agent_id": "default", "reason": "mock"}
    instance = exception_class("测试错误", payload)
    assert instance.error_code == error_code
    assert instance.http_status == http_status
    assert instance.details == payload


def test_error_codes_match_contract_schema():
    """异常类的 error_code 与 public/schema/knowledge.json 的 8 个错误码（去掉媒体超长）一致。"""
    contract_codes = {
        "KNOWLEDGE_ERROR",
        "KNOWLEDGE_VALIDATION_ERROR",
        "KNOWLEDGE_PARSE_FAILED",
        "KNOWLEDGE_UNSUPPORTED_MIME",
        "KNOWLEDGE_STORE_UNAVAILABLE",
        "KNOWLEDGE_ASR_UNAVAILABLE",
        "KNOWLEDGE_FFMPEG_UNAVAILABLE",
    }
    actual_codes = {exception_class("x").error_code for exception_class, _, _ in EXPECTED}
    assert actual_codes == contract_codes
