"""性能指标收集器 - 用于 LLM 端到端测试的性能指标记录与分析"""

import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class MetricRecord:
    """单条指标记录"""

    name: str
    value: float
    unit: str  # "ms", "tokens/s", "count", "ratio"
    timestamp: float
    threshold: Optional[float] = None  # 通过阈值
    passed: Optional[bool] = None  # 是否通过阈值检查


def calculate_percentiles(
    values: List[float], percentiles: List[int] = None
) -> Dict[str, float]:
    """计算百分位数。

    Args:
        values: 数值列表
        percentiles: 需要计算的百分位数列表，默认 [50, 90, 99]

    Returns:
        字典，键为 "p50"、"p90" 等，值为对应的百分位数
    """
    if percentiles is None:
        percentiles = [50, 90, 99]

    if not values:
        return {f"p{p}": 0.0 for p in percentiles}

    sorted_values = sorted(values)
    n = len(sorted_values)
    result: Dict[str, float] = {}

    for p in percentiles:
        # 使用线性插值法计算百分位数
        rank = (p / 100) * (n - 1)
        lower = int(rank)
        upper = min(lower + 1, n - 1)
        fraction = rank - lower
        interpolated = sorted_values[lower] + fraction * (
            sorted_values[upper] - sorted_values[lower]
        )
        result[f"p{p}"] = round(interpolated, 2)

    return result


class MetricsCollector:
    """性能指标收集器，用于记录和分析 LLM 端到端测试的各项性能指标。"""

    def __init__(self) -> None:
        self.records: List[MetricRecord] = []

    def record(
        self,
        name: str,
        value: float,
        unit: str,
        threshold: Optional[float] = None,
    ) -> None:
        """记录一条指标。如果提供了 threshold，自动判定通过/失败。

        Args:
            name: 指标名称
            value: 指标值
            unit: 单位（"ms", "tokens/s", "count", "ratio"）
            threshold: 通过阈值，提供时自动判定 passed
        """
        passed = None
        if threshold is not None:
            # 对于 "ms" 和 "count" 类型，值越低越好
            # 对于 "tokens/s" 和 "ratio" 类型，值越高越好
            if unit in ("tokens/s", "ratio"):
                passed = value >= threshold
            else:
                passed = value <= threshold

        self.records.append(
            MetricRecord(
                name=name,
                value=value,
                unit=unit,
                timestamp=time.time(),
                threshold=threshold,
                passed=passed,
            )
        )

    def record_response_time(
        self, endpoint: str, time_ms: float, threshold_ms: float = 120
    ) -> None:
        """记录 API 响应时间。

        Args:
            endpoint: API 端点名称
            time_ms: 响应时间（毫秒）
            threshold_ms: 通过阈值（毫秒），默认 120ms
        """
        self.record(
            name=f"response_time.{endpoint}",
            value=time_ms,
            unit="ms",
            threshold=threshold_ms,
        )

    def record_ttft(self, ttft_ms: float, threshold_ms: float = 5000) -> None:
        """记录首 token 时间（Time To First Token）。

        Args:
            ttft_ms: 首 token 时间（毫秒）
            threshold_ms: 通过阈值（毫秒），默认 5000ms
        """
        self.record(
            name="ttft",
            value=ttft_ms,
            unit="ms",
            threshold=threshold_ms,
        )

    def record_tps(self, tps: float, min_threshold: float = 5) -> None:
        """记录每秒 token 数（Tokens Per Second）。

        Args:
            tps: 每秒 token 数
            min_threshold: 最低通过阈值，默认 5 tokens/s
        """
        self.record(
            name="tps",
            value=tps,
            unit="tokens/s",
            threshold=min_threshold,
        )

    def record_concurrent(
        self,
        total: int,
        success: int,
        avg_time_ms: float,
        latencies_ms: List[float],
    ) -> None:
        """记录并发测试结果。自动计算 P50/P90/P99 延迟。

        Args:
            total: 总请求数
            success: 成功请求数
            avg_time_ms: 平均响应时间（毫秒）
            latencies_ms: 各请求延迟列表（毫秒）
        """
        success_rate = success / total if total > 0 else 0.0
        self.record(
            name="concurrent.success_rate",
            value=success_rate,
            unit="ratio",
            threshold=0.9,
        )
        self.record(
            name="concurrent.avg_time_ms",
            value=avg_time_ms,
            unit="ms",
        )

        percentiles = calculate_percentiles(latencies_ms)
        for pkey, pval in percentiles.items():
            self.record(
                name=f"concurrent.{pkey}",
                value=pval,
                unit="ms",
            )

    def get_summary(self) -> dict:
        """获取指标汇总，按类别分组。

        Returns:
            包含总计统计和分类详情的字典
        """
        total = len(self.records)
        passed = sum(1 for r in self.records if r.passed is True)
        failed = sum(1 for r in self.records if r.passed is False)
        pass_rate = passed / (passed + failed) if (passed + failed) > 0 else 1.0

        # 按类别分组
        categories: Dict[str, dict] = {
            "response_time": {"records": [], "avg": 0.0, "min": 0.0, "max": 0.0},
            "ttft": {"records": [], "avg": 0.0, "min": 0.0, "max": 0.0},
            "tps": {"records": [], "avg": 0.0, "min": 0.0, "max": 0.0},
            "concurrent": {
                "success_rate": 0.0,
                "avg_time_ms": 0.0,
                "p50": 0.0,
                "p90": 0.0,
                "p99": 0.0,
            },
        }

        # 分配记录到类别
        response_time_values: List[float] = []
        ttft_values: List[float] = []
        tps_values: List[float] = []

        for r in self.records:
            record_dict = asdict(r)
            if r.name.startswith("response_time."):
                categories["response_time"]["records"].append(record_dict)
                response_time_values.append(r.value)
            elif r.name == "ttft":
                categories["ttft"]["records"].append(record_dict)
                ttft_values.append(r.value)
            elif r.name == "tps":
                categories["tps"]["records"].append(record_dict)
                tps_values.append(r.value)
            elif r.name.startswith("concurrent."):
                if r.name == "concurrent.success_rate":
                    categories["concurrent"]["success_rate"] = r.value
                elif r.name == "concurrent.avg_time_ms":
                    categories["concurrent"]["avg_time_ms"] = r.value
                elif r.name == "concurrent.p50":
                    categories["concurrent"]["p50"] = r.value
                elif r.name == "concurrent.p90":
                    categories["concurrent"]["p90"] = r.value
                elif r.name == "concurrent.p99":
                    categories["concurrent"]["p99"] = r.value

        # 计算统计值
        if response_time_values:
            categories["response_time"]["avg"] = round(
                sum(response_time_values) / len(response_time_values), 2
            )
            categories["response_time"]["min"] = round(min(response_time_values), 2)
            categories["response_time"]["max"] = round(max(response_time_values), 2)

        if ttft_values:
            categories["ttft"]["avg"] = round(sum(ttft_values) / len(ttft_values), 2)
            categories["ttft"]["min"] = round(min(ttft_values), 2)
            categories["ttft"]["max"] = round(max(ttft_values), 2)

        if tps_values:
            categories["tps"]["avg"] = round(sum(tps_values) / len(tps_values), 2)
            categories["tps"]["min"] = round(min(tps_values), 2)
            categories["tps"]["max"] = round(max(tps_values), 2)

        return {
            "total_metrics": total,
            "passed_metrics": passed,
            "failed_metrics": failed,
            "pass_rate": round(pass_rate, 4),
            "categories": categories,
        }

    def check_degradation(
        self, metric_name: str, window: int = 10, threshold_pct: float = 0.5
    ) -> bool:
        """检查指标是否呈现退化趋势。

        比较最近 window 条记录的平均值与前 window 条记录的平均值，
        如果增长超过 threshold_pct（如 0.5 表示 50%），则认为存在退化。

        Args:
            metric_name: 指标名称（支持前缀匹配）
            window: 比较窗口大小
            threshold_pct: 退化判定阈值（比例）

        Returns:
            True 表示存在退化趋势
        """
        matching = [r for r in self.records if r.name == metric_name or r.name.startswith(f"{metric_name}.")]

        if len(matching) < 2 * window:
            return False

        first_window = matching[:window]
        last_window = matching[-window:]

        first_avg = sum(r.value for r in first_window) / len(first_window)
        last_avg = sum(r.value for r in last_window) / len(last_window)

        if first_avg == 0:
            return last_avg > 0

        increase_ratio = (last_avg - first_avg) / abs(first_avg)
        return increase_ratio > threshold_pct
