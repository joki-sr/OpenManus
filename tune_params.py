#!/usr/bin/env python3
"""
调参脚本：自动搜索最优参数组合
目标：最小化 test_perf/cocurrent/test0-100.py --procs=100 的运行时间
"""
import asyncio
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import json
import time

# 参数搜索空间（可以根据需要调整）
CPU_LIMIT_RANGE = [0.5, 1.0, 1.5, 2.0]  # CPU限制
MAX_SANDBOXES_RANGE = [5, 10, 20, 50]  # max_sandboxes_per_tag
MAX_CONCURRENCY_RANGE = [10, 20, 50, 100]  # max_concurrency_per_sandbox

# 如果只想快速测试，可以使用较小的搜索空间：
# CPU_LIMIT_RANGE = [0.5, 1.0, 2.0]
# MAX_SANDBOXES_RANGE = [5, 20]
# MAX_CONCURRENCY_RANGE = [20, 50]

# 文件路径
CONFIG_FILE = Path("app/config.py")
SHARED_POOL_FILE = Path("app/sandbox/core/shared_pool.py")
TEST_SCRIPT = Path("test_perf/cocurrent/test0-100.py")

# 备份文件
CONFIG_BACKUP = CONFIG_FILE.with_suffix(".py.backup")
SHARED_POOL_BACKUP = SHARED_POOL_FILE.with_suffix(".py.backup")


def backup_files():
    """备份原始文件"""
    if not CONFIG_BACKUP.exists():
        CONFIG_BACKUP.write_text(CONFIG_FILE.read_text())
        print(f"已备份: {CONFIG_FILE} -> {CONFIG_BACKUP}")
    if not SHARED_POOL_BACKUP.exists():
        SHARED_POOL_BACKUP.write_text(SHARED_POOL_FILE.read_text())
        print(f"已备份: {SHARED_POOL_FILE} -> {SHARED_POOL_BACKUP}")


def restore_files():
    """恢复原始文件"""
    if CONFIG_BACKUP.exists():
        CONFIG_FILE.write_text(CONFIG_BACKUP.read_text())
        CONFIG_BACKUP.unlink()
        print(f"已恢复: {CONFIG_FILE}")
    if SHARED_POOL_BACKUP.exists():
        SHARED_POOL_FILE.write_text(SHARED_POOL_BACKUP.read_text())
        SHARED_POOL_BACKUP.unlink()
        print(f"已恢复: {SHARED_POOL_FILE}")


def set_cpu_limit(cpu_limit: float):
    """设置cpu_limit默认值"""
    content = CONFIG_FILE.read_text()
    # 替换 cpu_limit 的默认值（匹配 Field(1.0, description=... 或 Field(1.0,description=...）
    pattern = r'cpu_limit: float = Field\([0-9.]+(?:\.0)?'
    replacement = f'cpu_limit: float = Field({cpu_limit}'
    content = re.sub(pattern, replacement, content)
    CONFIG_FILE.write_text(content)


def set_max_sandboxes(max_sandboxes: int):
    """设置max_sandboxes_per_tag默认值"""
    content = SHARED_POOL_FILE.read_text()
    # 替换 max_sandboxes_per_tag 的默认值
    pattern = r'max_sandboxes_per_tag: int = \d+'
    replacement = f'max_sandboxes_per_tag: int = {max_sandboxes}'
    content = re.sub(pattern, replacement, content)
    SHARED_POOL_FILE.write_text(content)


def set_max_concurrency(max_concurrency: int):
    """设置max_concurrency_per_sandbox默认值"""
    content = SHARED_POOL_FILE.read_text()
    # 替换 max_concurrency_per_sandbox 的默认值（可能是 int 或 None）
    pattern = r'max_concurrency_per_sandbox: Optional\[int\] = (?:None|\d+)'
    replacement = f'max_concurrency_per_sandbox: Optional[int] = {max_concurrency}'
    content = re.sub(pattern, replacement, content)
    SHARED_POOL_FILE.write_text(content)


def set_params(cpu_limit: float, max_sandboxes: int, max_concurrency: int):
    """设置所有参数"""
    set_cpu_limit(cpu_limit)
    set_max_sandboxes(max_sandboxes)
    set_max_concurrency(max_concurrency)


async def run_test() -> Tuple[float, str]:
    """
    运行测试并提取时间

    Returns:
        (time_value, output): 时间值和完整输出
    """
    cmd = [
        sys.executable,
        str(TEST_SCRIPT),
        "--procs=100"
    ]

    print(f"运行命令: {' '.join(cmd)}")

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )

    output_bytes, _ = await process.communicate()
    output = output_bytes.decode('utf-8', errors='ignore')

    # 查找所有 time=xxx.xxxs 的模式
    time_value = None
    lines = output.split('\n')

    # 方法1: 查找 "所有 agent 结束" 后的所有time值，取最后一个
    found_done = False
    last_time = None
    for i, line in enumerate(lines):
        if "所有 agent 结束" in line or "所有agent结束" in line:
            found_done = True
            # 继续查找后续的time值
            for j in range(i + 1, len(lines)):
                match = re.search(r'time=([0-9.]+)s', lines[j])
                if match:
                    last_time = float(match.group(1))

    if found_done and last_time is not None:
        time_value = last_time
    else:
        # 方法2: 如果没找到，尝试在整个输出中查找最后一个 time=xxx.xxxs
        matches = list(re.finditer(r'time=([0-9.]+)s', output))
        if matches:
            time_value = float(matches[-1].group(1))

    return time_value, output


async def test_params(cpu_limit: float, max_sandboxes: int, max_concurrency: int) -> Dict:
    """测试一组参数"""
    print(f"\n{'='*60}")
    print(f"测试参数组合:")
    print(f"  cpu_limit={cpu_limit}")
    print(f"  max_sandboxes_per_tag={max_sandboxes}")
    print(f"  max_concurrency_per_sandbox={max_concurrency}")
    print(f"{'='*60}")

    # 设置参数
    set_params(cpu_limit, max_sandboxes, max_concurrency)

    # 运行测试
    try:
        time_value, output = await run_test()

        result = {
            "cpu_limit": cpu_limit,
            "max_sandboxes_per_tag": max_sandboxes,
            "max_concurrency_per_sandbox": max_concurrency,
            "time": time_value,
            "success": time_value is not None
        }

        if time_value is not None:
            print(f"✓ 测试完成，时间: {time_value:.3f}s")
        else:
            print(f"✗ 测试失败，无法提取时间值")
            print("输出片段:")
            print(output[-500:] if len(output) > 500 else output)
            result["error"] = "无法提取时间值"

        return result

    except Exception as e:
        print(f"✗ 测试异常: {e}")
        return {
            "cpu_limit": cpu_limit,
            "max_sandboxes_per_tag": max_sandboxes,
            "max_concurrency_per_sandbox": max_concurrency,
            "time": None,
            "success": False,
            "error": str(e)
        }


async def grid_search():
    """网格搜索最优参数"""
    print("="*60)
    print("开始网格搜索最优参数")
    print("="*60)

    backup_files()

    results = []
    total_tests = len(CPU_LIMIT_RANGE) * len(MAX_SANDBOXES_RANGE) * len(MAX_CONCURRENCY_RANGE)
    current_test = 0

    try:
        for cpu_limit in CPU_LIMIT_RANGE:
            for max_sandboxes in MAX_SANDBOXES_RANGE:
                for max_concurrency in MAX_CONCURRENCY_RANGE:
                    current_test += 1
                    print(f"\n进度: {current_test}/{total_tests}")

                    result = await test_params(cpu_limit, max_sandboxes, max_concurrency)
                    results.append(result)

                    # 保存中间结果
                    save_results(results)

                    # 短暂休息，避免系统过载，并等待sandbox清理
                    print("等待系统清理...")
                    await asyncio.sleep(5)

        # 恢复原始文件
        restore_files()

        # 分析结果
        analyze_results(results)

    except KeyboardInterrupt:
        print("\n\n用户中断，正在恢复文件...")
        restore_files()
        print("已保存中间结果，可以查看 results.json")
        raise
    except Exception as e:
        print(f"\n\n发生错误: {e}")
        restore_files()
        raise


def save_results(results: List[Dict]):
    """保存结果到JSON文件"""
    results_file = Path("tune_results.json")
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"结果已保存到: {results_file}")


def analyze_results(results: List[Dict]):
    """分析结果并输出最优参数"""
    print("\n" + "="*60)
    print("结果分析")
    print("="*60)

    # 过滤成功的测试
    successful_results = [r for r in results if r.get("success") and r.get("time") is not None]

    if not successful_results:
        print("没有成功的测试结果！")
        return

    # 按时间排序
    successful_results.sort(key=lambda x: x["time"])

    print(f"\n总共测试: {len(results)} 组参数")
    print(f"成功: {len(successful_results)} 组")
    print(f"失败: {len(results) - len(successful_results)} 组")

    print("\n最优的5组参数:")
    print("-" * 60)
    for i, result in enumerate(successful_results[:5], 1):
        print(f"{i}. 时间: {result['time']:.3f}s")
        print(f"   cpu_limit={result['cpu_limit']}")
        print(f"   max_sandboxes_per_tag={result['max_sandboxes_per_tag']}")
        print(f"   max_concurrency_per_sandbox={result['max_concurrency_per_sandbox']}")
        print()

    # 最优参数
    best = successful_results[0]
    print("="*60)
    print("最优参数组合:")
    print(f"  cpu_limit={best['cpu_limit']}")
    print(f"  max_sandboxes_per_tag={best['max_sandboxes_per_tag']}")
    print(f"  max_concurrency_per_sandbox={best['max_concurrency_per_sandbox']}")
    print(f"  运行时间: {best['time']:.3f}s")
    print("="*60)

    # 保存最优参数
    best_file = Path("best_params.json")
    with open(best_file, 'w', encoding='utf-8') as f:
        json.dump(best, f, indent=2, ensure_ascii=False)
    print(f"最优参数已保存到: {best_file}")


async def main():
    """主函数"""
    if not TEST_SCRIPT.exists():
        print(f"错误: 测试脚本不存在: {TEST_SCRIPT}")
        sys.exit(1)

    if not CONFIG_FILE.exists():
        print(f"错误: 配置文件不存在: {CONFIG_FILE}")
        sys.exit(1)

    if not SHARED_POOL_FILE.exists():
        print(f"错误: 共享池文件不存在: {SHARED_POOL_FILE}")
        sys.exit(1)

    print("调参脚本")
    print("="*60)
    print(f"参数搜索空间:")
    print(f"  cpu_limit: {CPU_LIMIT_RANGE}")
    print(f"  max_sandboxes_per_tag: {MAX_SANDBOXES_RANGE}")
    print(f"  max_concurrency_per_sandbox: {MAX_CONCURRENCY_RANGE}")
    print(f"  总组合数: {len(CPU_LIMIT_RANGE) * len(MAX_SANDBOXES_RANGE) * len(MAX_CONCURRENCY_RANGE)}")
    print("="*60)

    await grid_search()


if __name__ == "__main__":
    asyncio.run(main())

