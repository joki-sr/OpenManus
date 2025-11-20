import asyncio
import csv
import os
import sys
import time

import psutil


# ============================ 参数 ==============================
def parse_agent_count():
    if len(sys.argv) < 2:
        print("用法: python test_and_draw.py <AGENT_COUNT>")
        sys.exit(1)
    try:
        n = int(sys.argv[1])
        assert n >= 0
        return n
    except:
        print("AGENT_COUNT 必须是 >=0 的整数")
        sys.exit(1)

AGENT_COUNT = parse_agent_count()
TASK_PROMPT = "请利用python_execute工具，写python代码并计算前1000个素数"
MONITOR_INTERVAL = 0.5
PYTHON_TOOL = "/mnt/e/Development/AgentAI/OpenManus/.venv/bin/python"
MAIN_PY = "/mnt/e/Development/AgentAI/OpenManus/main.py"

# 输出
TIMESTAMP = time.strftime("%Y%m%d%H%M%S")
OUTPUT_DIR = "/mnt/e/Development/AgentAI/OpenManus/test_perf/cocurrent/data"
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_CSV = f"{OUTPUT_DIR}/{TIMESTAMP}_{AGENT_COUNT}.csv"
# ============================ 参数 ==============================


# ======================= 启动一个 agent =======================
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
        writer.writerow(["time_s", "cpu_percent", "memory_mb"])

        while True:
            now = time.time() - start_time
            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory().used / (1024 * 1024)

            print(f"time={now:.3f}s | CPU={cpu:.1f}% | MEM={mem:.1f}MB")
            writer.writerow([round(now, 3), round(cpu, 1), round(mem, 1)])

            # --- benchmark 模式，只跑 30s ---
            if is_benchmark and now >= 30:
                print("[Monitor] Benchmark finished (30s)")
                break

            # --- 正常 agent 模式：等待所有进程结束 ---
            if not is_benchmark and done_flag.is_set():
                print("[Monitor] All agents completed.")
                break

            await asyncio.sleep(MONITOR_INTERVAL)

    print(f"[Monitor] data saved: {OUTPUT_CSV}")


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
