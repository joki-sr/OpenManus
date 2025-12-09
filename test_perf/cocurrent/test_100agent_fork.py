import argparse
import asyncio
import csv
import os
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import psutil


# ============================ 参数 ==============================
def parse_args():
    parser = argparse.ArgumentParser(description="并发 agent 压测脚本（fork模式，100个agent）")
    parser.add_argument(
        "--aff",
        type=int,
        help="是否对主进程绑核（可选，main_100agent_fork.py内部已对子进程绑核）",
    )
    args = parser.parse_args()
    return args


ARGS = parse_args()
AFF_MODE = ARGS.aff
TASK_PROMPT = "请利用python_execute工具，写python代码并计算前1000个素数"
MONITOR_INTERVAL = 0.5
PYTHON_TOOL = "/home/zhangsiyi/AgenticAI/OpenManus/.venv/bin/python"
MAIN_PY = "/home/zhangsiyi/AgenticAI/OpenManus/main_100agent_fork.py"
CPU_SUM_CORES = psutil.cpu_count(logical=True)
CPU_CORES = min(AFF_MODE if AFF_MODE is not None else 0, CPU_SUM_CORES)

# 输出
TIMESTAMP = time.strftime("%Y%m%d%H%M%S")
OUTPUT_DIR = "/home/zhangsiyi/AgenticAI/OpenManus/test_perf/cocurrent/data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# main_100agent_fork.py 内部固定启动 100 个 agent
AGENT_COUNT = 100

if AFF_MODE is None:
    OUTPUT_CSV = f"{OUTPUT_DIR}/{TIMESTAMP}_{AGENT_COUNT}.csv"
elif AFF_MODE != 0:
    OUTPUT_CSV = f"{OUTPUT_DIR}/{TIMESTAMP}_{AGENT_COUNT}_aff{CPU_CORES}.csv"
else:  # AFF_MODE == 0:
    OUTPUT_CSV = f"{OUTPUT_DIR}/{TIMESTAMP}_{AGENT_COUNT}_noaff.csv"
# ============================ 参数 ==============================


# ======================= 启动主进程（内部会fork 100个子进程）=======================
async def run_main_process():
    """启动 main_100agent_fork.py 主进程（内部会fork 100个子进程）"""
    print(f"[Main Process] Starting main_100agent_fork.py (will fork 100 child processes)...")

    # 主进程不输出到终端
    proc = await asyncio.create_subprocess_exec(
        PYTHON_TOOL, MAIN_PY, "--prompt", TASK_PROMPT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    # # 主进程输出到终端
    # proc = await asyncio.create_subprocess_exec(
    #     PYTHON_TOOL, MAIN_PY, "--prompt", TASK_PROMPT
    # )

    # 如果AFF（对主进程绑核，虽然子进程内部已经各自绑核）
    if AFF_MODE is not None and AFF_MODE != 0:
        print(f"[Main Process] bind core: 0")
        psutil.Process(proc.pid).cpu_affinity([0])

    return proc


# ======================= 监控 =======================
async def monitor_loop(proc, done_flag: asyncio.Event, is_benchmark: bool):
    """
    proc: asyncio.Process，主进程
    done_flag: 主进程结束时由 main 设置
    """
    print("[Monitor] started.")
    start_time = time.time()

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s", "cpu_percent", "memory_mb", "cur_time"])

        while True:
            now = time.time() - start_time
            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory().used / (1024 * 1024)

            cur_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"time={now:.3f}s | CPU={cpu:.1f}% | MEM={mem:.1f}MB | CUR={cur_time}")
            writer.writerow([round(now, 3), round(cpu, 1), round(mem, 1), cur_time])

            # --- benchmark 模式，只跑 30s ---
            if is_benchmark and now >= 30:
                print("[Monitor] Benchmark finished (30s)")
                break

            # --- 正常 agent 模式：等待主进程结束 ---
            if not is_benchmark and done_flag.is_set():
                print("[Monitor] Main process completed.")
                break

            await asyncio.sleep(MONITOR_INTERVAL)

    print(f"[Monitor] data saved:\n{OUTPUT_CSV}")


# ======================= 主流程 =======================
async def main():
    done_flag = asyncio.Event()

    # 1. 启动 monitor，不等主进程启动
    monitor_task = asyncio.create_task(
        monitor_loop(
            None,  # proc 会在后面设置
            done_flag,
            is_benchmark=False  # 总是等待主进程完成
        )
    )

    # 2. 启动主进程（内部会fork 100个子进程）
    print(f"启动 main_100agent_fork.py（将fork {AGENT_COUNT} 个子进程）...")
    proc = await run_main_process()

    # 等主进程结束（主进程会等待所有子进程完成）
    await proc.wait()
    print("主进程结束（所有子进程已完成）")

    # 通知 monitor 可以停止了
    done_flag.set()

    # 3. 等 monitor 完成写入
    await monitor_task


if __name__ == "__main__":
    asyncio.run(main())
    DRAW_SCRIPT = "/home/zhangsiyi/AgenticAI/OpenManus/test_perf/cocurrent/draw.py"
    subprocess.run([PYTHON_TOOL, DRAW_SCRIPT, f"--path={OUTPUT_CSV}"])

