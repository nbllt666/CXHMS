"""测试报告生成器 - 生成控制台摘要和 JSON 详细报告"""

import json
import os
from datetime import datetime
from dataclasses import asdict
from typing import List

from .runner import ScenarioResult, StepResult

# ANSI 颜色代码
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_RESET = "\033[0m"
_BOLD = "\033[1m"


class ReportGenerator:
    """测试报告生成器，输出控制台摘要和 JSON 详细报告。"""

    def __init__(self, results: List[ScenarioResult], output_dir: str = "test_reports") -> None:
        self.results = results
        self.output_dir = output_dir

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _status_text(passed: bool) -> str:
        if passed:
            return f"{_GREEN}PASS{_RESET}"
        return f"{_RED}FAIL{_RESET}"

    @staticmethod
    def _avg_response_time(result: ScenarioResult) -> float:
        """计算场景中所有步骤的平均响应时间（毫秒）。"""
        if not result.steps:
            return 0.0
        total = sum(s.response_time_ms for s in result.steps)
        return total / len(result.steps)

    @staticmethod
    def _step_to_dict(step: StepResult) -> dict:
        return asdict(step)

    # ------------------------------------------------------------------
    # 控制台摘要
    # ------------------------------------------------------------------

    def print_summary(self) -> None:
        """打印彩色控制台测试摘要。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print()
        print("=" * 60)
        print(f"  {_BOLD}CXHMS LLM E2E 测试报告{_RESET}")
        print(f"  时间: {now}")
        print("=" * 60)

        print()
        print("场景结果:")

        for result in self.results:
            status = self._status_text(result.passed)
            avg_rt = self._avg_response_time(result)
            line = f"  [{status}] {result.name:<20s}  评分: {result.score:.1f}  平均响应: {avg_rt:.0f}ms"
            print(line)

            # 失败场景打印错误信息（截断至 200 字符）
            if not result.passed and result.error:
                truncated = result.error[:200] + ("..." if len(result.error) > 200 else "")
                print(f"        {_YELLOW}错误: {truncated}{_RESET}")

        print()
        print("-" * 60)

        # 总体统计
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0.0
        avg_score = (sum(r.score for r in self.results) / total) if total > 0 else 0.0

        print("总体结果:")
        print(
            f"  总场景数: {total}    "
            f"通过: {_GREEN}{passed}{_RESET}    "
            f"失败: {_RED}{failed}{_RESET}    "
            f"通过率: {pass_rate:.1f}%"
        )
        print(f"  平均评分: {avg_score:.1f}/5.0")
        print("=" * 60)
        print()

    # ------------------------------------------------------------------
    # JSON 详细报告
    # ------------------------------------------------------------------

    def generate_json_report(self) -> str:
        """生成 JSON 详细报告文件并返回文件路径。"""
        os.makedirs(self.output_dir, exist_ok=True)

        now = datetime.now()
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        filename = f"llm_e2e_report_{timestamp_str}.json"
        filepath = os.path.join(self.output_dir, filename)

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        pass_rate = (passed / total) if total > 0 else 0.0
        avg_score = (sum(r.score for r in self.results) / total) if total > 0 else 0.0
        overall_score = avg_score

        scenarios_data = []
        for result in self.results:
            scenarios_data.append({
                "name": result.name,
                "description": result.description,
                "passed": result.passed,
                "score": result.score,
                "metrics": result.metrics,
                "steps": [self._step_to_dict(s) for s in result.steps],
                "error": result.error,
            })

        report = {
            "report_info": {
                "timestamp": now.isoformat(),
                "total_scenarios": total,
                "passed": passed,
                "failed": failed,
            },
            "overall_score": round(overall_score, 2),
            "pass_rate": round(pass_rate, 4),
            "scenarios": scenarios_data,
            "summary": {
                "total_scenarios": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": round(pass_rate, 4),
                "avg_score": round(avg_score, 2),
                "scenario_details": [
                    {
                        "name": r.name,
                        "passed": r.passed,
                        "score": r.score,
                    }
                    for r in self.results
                ],
            },
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return filepath

    # ------------------------------------------------------------------
    # 统一生成
    # ------------------------------------------------------------------

    def generate(self) -> str:
        """生成控制台摘要和 JSON 报告，返回 JSON 报告路径。"""
        self.print_summary()
        return self.generate_json_report()
