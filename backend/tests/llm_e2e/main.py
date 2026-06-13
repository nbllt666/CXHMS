"""CXHMS LLM 端到端测试框架 - 主入口脚本"""

import argparse
import asyncio
import sys
from typing import List

from .config import TestConfig
from .runner import TestRunner, ScenarioFunc
from .scenarios import ALL_SCENARIOS
from .report import ReportGenerator
from .client import CXHMSClient

SCENARIO_NAMES: List[str] = [s.__name__ for s in ALL_SCENARIOS]


async def _check_health(config: TestConfig) -> bool:
    """检查 CXHMS 服务健康状态。返回 True 表示健康。"""
    try:
        async with CXHMSClient(
            base_url=config.cxhms_base_url,
            timeout=10,
        ) as client:
            health = await client.check_health()
            print(f"  服务健康检查: {health.get('status', 'unknown')}")
            return True
    except Exception as exc:
        print(f"  \033[91m服务健康检查失败: {exc}\033[0m")
        print(f"  请确认 CXHMS 服务正在运行: {config.cxhms_base_url}")
        return False


async def run(config: TestConfig, scenarios: List[ScenarioFunc], verbose: bool = False) -> int:
    """运行测试套件。全部通过返回 0，否则返回 1。"""
    # 1. 打印配置信息
    print()
    print("=" * 60)
    print("  CXHMS LLM 端到端测试框架")
    print("=" * 60)
    print(f"  CXHMS 服务地址:     {config.cxhms_base_url}")
    print(f"  评判服务地址:       {config.judge_vllm_base_url}")
    print(f"  评判模型:           {config.judge_model}")
    print(f"  并发用户数:         {config.concurrent_users}")
    print(f"  长对话轮数:         {config.long_conversation_rounds}")
    print(f"  请求超时:           {config.chat_timeout}s")
    print(f"  待运行场景数:       {len(scenarios)}")
    print("=" * 60)
    print()

    # 2. 检查 CXHMS 服务健康状态
    print("正在检查 CXHMS 服务...")
    if not await _check_health(config):
        return 1
    print()

    # 3. 运行所有场景
    runner = TestRunner(config)

    for i, scenario in enumerate(scenarios, 1):
        name = getattr(scenario, "__name__", str(scenario))
        print(f"  [{i}/{len(scenarios)}] 运行场景: {name} ...", end="", flush=True)

        result = await runner.run_scenario(scenario)

        if result.passed:
            print(f" \033[92m通过\033[0m (评分: {result.score:.1f})")
        else:
            print(f" \033[91m失败\033[0m (评分: {result.score:.1f})")

        # 详细日志：始终显示步骤摘要
        for step in result.steps:
            status = "\033[92mPASS\033[0m" if step.passed else "\033[91mFAIL\033[0m"
            print(f"    [{status}] {step.name} (评分: {step.score:.1f}, 响应时间: {step.response_time_ms:.0f}ms)")
            if step.error:
                print(f"           错误: {step.error[:300]}")
            if step.details and verbose:
                for k, v in step.details.items():
                    v_str = str(v)
                    if len(v_str) > 500:
                        v_str = v_str[:500] + "..."
                    print(f"           {k}: {v_str}")

        if result.error and verbose:
            print(f"         场景错误: {result.error[:300]}")

    print()

    # 4. 生成报告
    results = runner.results
    report_gen = ReportGenerator(results, output_dir=config.report_output_dir)
    json_path = report_gen.generate()
    print(f"详细报告已保存至: {json_path}")

    # 5. 返回退出码
    all_passed = all(r.passed for r in results)
    return 0 if all_passed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="CXHMS LLM 端到端测试框架")
    parser.add_argument(
        "--url",
        default=None,
        help="CXHMS 服务地址 (默认: http://localhost:8001)",
    )
    parser.add_argument(
        "--judge-url",
        default=None,
        help="vLLM 评判服务地址 (默认: http://localhost:8000/v1)",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="评判模型名称 (默认: gemma4)",
    )
    parser.add_argument(
        "--scenarios",
        nargs="*",
        default=None,
        help=f"要运行的场景 (可选: {', '.join(SCENARIO_NAMES)})",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=None,
        help="并发用户数",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=None,
        help="长对话轮数",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="请求超时(秒)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="报告输出目录",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="详细输出",
    )

    args = parser.parse_args()

    # 从环境变量构建配置，再用 CLI 参数覆盖
    config = TestConfig.from_env()
    if args.url:
        config.cxhms_base_url = args.url
    if args.judge_url:
        config.judge_vllm_base_url = args.judge_url
    if args.judge_model:
        config.judge_model = args.judge_model
    if args.concurrent:
        config.concurrent_users = args.concurrent
    if args.rounds:
        config.long_conversation_rounds = args.rounds
    if args.timeout:
        config.chat_timeout = args.timeout
    if args.output:
        config.report_output_dir = args.output

    # 选择场景
    scenarios: List[ScenarioFunc] = list(ALL_SCENARIOS)
    if args.scenarios:
        name_to_scenario = {s.__name__: s for s in ALL_SCENARIOS}
        selected: List[ScenarioFunc] = []
        for name in args.scenarios:
            if name in name_to_scenario:
                selected.append(name_to_scenario[name])
            else:
                print(f"警告: 未知场景 '{name}'，可用场景: {', '.join(SCENARIO_NAMES)}")
        if selected:
            scenarios = selected

    exit_code = asyncio.run(run(config, scenarios, args.verbose))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
