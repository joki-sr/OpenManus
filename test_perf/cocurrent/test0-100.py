import argparse
import asyncio
import csv
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import psutil


# ============================ 参数 ==============================
def parse_args():
    parser = argparse.ArgumentParser(description="并发 agent 压测脚本")
    parser.add_argument(
        "--procs",
        type=int,
        help="需要启动的 agent 数量 (>=0)",
    )
    parser.add_argument(
        "--aff",
        type=int,
        # choices=[0, 1],
        help="是否对每个子进程绑核，1=绑定，0=不绑定",
    )
    args = parser.parse_args()

    if args.procs is None:
        parser.error("输入并发数")
    if args.procs < 0:
        parser.error("num大于等于0")

    return args


ARGS = parse_args()
AGENT_COUNT = ARGS.procs
AFF_MODE = ARGS.aff
TASK_PROMPT = "请利用python_execute工具，写python代码并计算前1000个素数"
MONITOR_INTERVAL = 0.5
PYTHON_TOOL = "/home/zhangsiyi/AgenticAI/OpenManus/.venv/bin/python"
MAIN_PY = "/home/zhangsiyi/AgenticAI/OpenManus/main.py"
CPU_SUM_CORES = psutil.cpu_count(logical=True)
CPU_CORES = min(AFF_MODE if AFF_MODE is not None else 0, CPU_SUM_CORES)

# 输出
TIMESTAMP = time.strftime("%Y%m%d%H%M%S")
OUTPUT_DIR = "/home/zhangsiyi/AgenticAI/OpenManus/test_perf/cocurrent/data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

if AFF_MODE is None:
    OUTPUT_CSV = f"{OUTPUT_DIR}/{TIMESTAMP}_{AGENT_COUNT}.csv"
elif AFF_MODE != 0:
    OUTPUT_CSV = f"{OUTPUT_DIR}/{TIMESTAMP}_{AGENT_COUNT}_aff{CPU_CORES}.csv"
else:#  AFF_MODE == 0:
    OUTPUT_CSV = f"{OUTPUT_DIR}/{TIMESTAMP}_{AGENT_COUNT}_noaff.csv"
# ============================ 参数 ==============================


# ======================= 启动一个 agent =======================
# print(f"CPU_CORES: {CPU_CORES}")
async def run_agent(agent_id: int):
    print(f"[Agent {agent_id}] start.")

    # agent不输出到终端
    proc = await asyncio.create_subprocess_exec(
        PYTHON_TOOL, MAIN_PY, "--prompt", TASK_PROMPT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    # # agent输出到终端
    # proc = await asyncio.create_subprocess_exec(
    #     PYTHON_TOOL, MAIN_PY , "--prompt", TASK_PROMPT
    # )


    # 如果AFF
    if AFF_MODE is not None and AFF_MODE != 0 :
        print(f"[Agent {agent_id}] bind core: {agent_id % CPU_CORES}")
        psutil.Process(proc.pid).cpu_affinity([agent_id % CPU_CORES])

    return proc


# ======================= 监控 =======================
async def monitor_loop(procs: list, done_flag: asyncio.Event, is_benchmark: bool):
    """
    procs: list[asyncio.Process]，Agent 列表，会在外部启动后 append 进来
    done_flag: 所有 agent 结束时由 main 设置
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

            # --- 正常 agent 模式：等待所有进程结束 ---
            if not is_benchmark and done_flag.is_set():
                print("[Monitor] All agents completed.")
                break

            await asyncio.sleep(MONITOR_INTERVAL)

    print(f"[Monitor] data saved:\n{OUTPUT_CSV}")


# ======================= 主流程 =======================
async def main():
    procs = []
    done_flag = asyncio.Event()

    # 1. 启动 monitor，不等 agent 启动
    monitor_task = asyncio.create_task(
        monitor_loop(
            procs,
            done_flag,
            is_benchmark=(AGENT_COUNT == 0)
        )
    )

    # 2. 启动 agent（如果数量>0）
    if AGENT_COUNT > 0:
        print(f"启动 {AGENT_COUNT} 个 agent...")
        new_procs = await asyncio.gather(*[run_agent(i) for i in range(AGENT_COUNT)])
        procs.extend(new_procs)

        # 等所有 agent 结束
        await asyncio.gather(*[p.wait() for p in procs])
        print("所有 agent 结束")

        # 通知 monitor 可以停止了
        done_flag.set()
    else:
        print("AGENT_COUNT = 0，进入基准监控模式（30s）")

    # 3. 等 monitor 完成写入
    await monitor_task


if __name__ == "__main__":
    asyncio.run(main())
