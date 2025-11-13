import asyncio
import os
import sys
import time
from pathlib import Path
from statistics import mean, stdev
from typing import List, Tuple

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.config import SandboxSettings
from app.sandbox.core.sandbox import DockerSandbox


async def measure_sandbox_ops(test_times: int = 10) -> Tuple[List[float], List[float]]:
    """测量sandbox的创建和清理时间

    Args:
        test_times: 测试次数

    Returns:
        Tuple[List[float], List[float]]: 创建时间列表和清理时间列表
    """
    create_times = []
    cleanup_times = []

    config = SandboxSettings()

    for i in range(test_times):
        print(f"\rRunning test {i+1}/{test_times}", end="")

        # 测量创建时间
        t1 = time.time()
        sandbox = DockerSandbox(config)
        await sandbox.create()
        t2 = time.time()
        create_times.append(t2 - t1)

        # 测量清理时间
        t3 = time.time()
        await sandbox.cleanup()
        t4 = time.time()
        cleanup_times.append(t4 - t3)

        # 等待一小段时间确保资源完全释放
        await asyncio.sleep(1)

    print("\n")  # 清除进度显示
    return create_times, cleanup_times


def print_stats(operation: str, times: List[float]) -> None:
    """打印操作的统计信息

    Args:
        operation: 操作名称
        times: 时间列表
    """
    avg_time = mean(times)
    std_time = stdev(times) if len(times) > 1 else 0
    min_time = min(times)
    max_time = max(times)

    print(f"{operation} Statistics:")
    print(f"  Average Time: {avg_time:.3f}s")
    print(f"  Std Dev:     {std_time:.3f}s")
    print(f"  Min Time:    {min_time:.3f}s")
    print(f"  Max Time:    {max_time:.3f}s")
    print(f"  All Times:   {', '.join(f'{t:.3f}' for t in times)}s")
    print()


async def main():
    """主函数"""
    test_times = 1
    print(f"Starting sandbox performance test with {test_times} iterations\n")

    try:
        create_times, cleanup_times = await measure_sandbox_ops(test_times)

        # 打印统计信息
        print_stats("Sandbox Creation", create_times)
        print_stats("Sandbox Cleanup", cleanup_times)

        # 打印总体统计
        total_times = [sum(x) for x in zip(create_times, cleanup_times)]
        print_stats("Total Operation (Create + Cleanup)", total_times)

    except Exception as e:
        print(f"Error during test: {e}")


if __name__ == "__main__":
    asyncio.run(main())
