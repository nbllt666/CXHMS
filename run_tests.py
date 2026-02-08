#!/usr/bin/env python3
"""
CXHMS 测试运行器
运行所有前端和后端测试
"""
import subprocess
import sys
import os
from pathlib import Path


def run_frontend_tests():
    """运行前端测试"""
    print("=" * 60)
    print("运行前端测试...")
    print("=" * 60)

    frontend_dir = Path(__file__).parent / "frontend"

    # 检测 npm 命令 (Windows 使用 npm.cmd)
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"

    # 检查前端依赖是否已安装
    node_modules = frontend_dir / "node_modules"
    if not node_modules.exists():
        print("\n📦 安装前端依赖...")
        result = subprocess.run(
            [npm_cmd, "install"],
            cwd=frontend_dir,
            capture_output=True,
            text=True,
            shell=True
        )
        if result.returncode != 0:
            print(f"❌ 安装依赖失败: {result.stderr}")
            return False
        print("✅ 依赖安装完成")
    else:
        print("\n✅ 前端依赖已安装")

    # 运行测试
    print("\n🧪 运行前端测试...")
    result = subprocess.run(
        [npm_cmd, "test"],
        cwd=frontend_dir,
        capture_output=False,
        shell=True
    )

    if result.returncode == 0:
        print("✅ 前端测试通过")
        return True
    else:
        print("❌ 前端测试失败")
        return False


def run_backend_tests():
    """运行后端测试"""
    print("\n" + "=" * 60)
    print("运行后端测试...")
    print("=" * 60)

    # 运行 pytest
    print("\n🧪 运行后端测试...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests", "-v"],
        capture_output=False
    )

    if result.returncode == 0:
        print("✅ 后端测试通过")
        return True
    else:
        print("❌ 后端测试失败")
        return False


def run_backend_tests_with_coverage():
    """运行后端测试并生成覆盖率报告"""
    print("\n" + "=" * 60)
    print("运行后端测试 (带覆盖率)...")
    print("=" * 60)

    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "backend/tests",
            "-v",
            "--cov=backend",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov"
        ],
        capture_output=False
    )

    if result.returncode == 0:
        print("✅ 后端测试通过")
        print("📊 覆盖率报告已生成: htmlcov/index.html")
        return True
    else:
        print("❌ 后端测试失败")
        return False


def run_specific_test(test_path):
    """运行特定测试"""
    print(f"\n🧪 运行测试: {test_path}")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_path, "-v"],
        capture_output=False
    )
    return result.returncode == 0


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="CXHMS 测试运行器")
    parser.add_argument(
        "--frontend-only",
        action="store_true",
        help="只运行前端测试"
    )
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help="只运行后端测试"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="生成覆盖率报告"
    )
    parser.add_argument(
        "--test",
        type=str,
        help="运行特定测试文件或目录"
    )

    args = parser.parse_args()

    print("\n" + "🚀" * 30)
    print("   CXHMS 测试套件")
    print("🚀" * 30 + "\n")

    success = True

    if args.test:
        success = run_specific_test(args.test)
    elif args.frontend_only:
        success = run_frontend_tests()
    elif args.backend_only:
        if args.coverage:
            success = run_backend_tests_with_coverage()
        else:
            success = run_backend_tests()
    else:
        # 运行所有测试
        frontend_success = run_frontend_tests()
        if args.coverage:
            backend_success = run_backend_tests_with_coverage()
        else:
            backend_success = run_backend_tests()
        success = frontend_success and backend_success

    print("\n" + "=" * 60)
    if success:
        print("✅ 所有测试通过!")
        print("=" * 60)
        return 0
    else:
        print("❌ 部分测试失败")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
