"""
1. 创建一个任务（计算1000个素数）
2. 并发启动100个agent，每个agent都执行这个任务(也可以设定为0，测主机空闲情况下)
3. 每个agent都在自己的sandbox中执行
4. 收集指标：每0.5s,采集启动时间、执行时间、CPU使用率、内存使用
5. 数据保存到csv。
"""
import asyncio
import psutil
import time
import csv
import os

# ---------------------- 配置参数 ----------------------
AGENT_COUNT = 0  # 支持 0/1/100+，0 时采集主机基准指标
TASK_PROMPT = "请利用python_execute工具，写python代码并计算前1000个素数"
MONITOR_INTERVAL = 0.5  # 秒
TIMESTAMP = time.strftime("%Y%m%d%H%M%S")
OUTPUT_DIR = "/mnt/e/Development/AgentAI/OpenManus/test_perf/cocurrent/data"
OUTPUT_CSV = f"{OUTPUT_DIR}/{TIMESTAMP}_{AGENT_COUNT}.csv"

# 确保输出目录存在
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def run_agent(agent_id: int):
    print(f"Agent {agent_id} starts.")
    """启动单个Agent进程，返回进程对象"""
    proc = await asyncio.create_subprocess_exec(
        "python", "main.py", "--prompt", TASK_PROMPT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    return proc

async def monitor_procs(procs, is_benchmark: bool = False):
    """
    监控进程资源（兼容空进程列表/基准监控）
    :param procs: Agent进程列表
    :param is_benchmark: 是否是基准监控（无Agent时）
    """
    start_time = time.time()
    ps_procs = []

    # 绑定Agent进程（非基准监控时）
    if not is_benchmark and procs:
        for p in procs:
            try:
                if psutil.pid_exists(p.pid):
                    ps_procs.append(psutil.Process(p.pid))
                else:
                    print(f"警告：Agent进程（pid={p.pid}）启动后立即退出")
            except psutil.NoSuchProcess:
                print(f"警告：Agent进程（pid={p.pid}）未找到")
        finished = [False] * len(ps_procs)
    else:
        # 基准监控（无Agent）：标记为"永远未完成"，持续采集主机指标
        finished = [False] if is_benchmark else []

    # 打开CSV文件写入数据
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s", "cpu_percent", "memory_mb"])

        while not all(finished):
            current_time = time.time() - start_time
            total_cpu = 0.0
            total_mem = 0.0

            ################################累加，感觉不合适########################################
            # if is_benchmark:
            #     # 场景1：无Agent（基准监控）- 采集主机总CPU/内存
            #     total_cpu = psutil.cpu_percent(interval=0)  # 主机总CPU使用率
            #     total_mem = psutil.virtual_memory().used / (1024 * 1024)  # 主机已用内存
            # else:
            #     # 场景2：有Agent - 采集所有Agent进程总资源
            #     for i, p in enumerate(ps_procs):
            #         if finished[i]:
            #             continue
            #         try:
            #             if p.is_running():
            #                 # 修复：interval=0 避免缓存导致数据不准
            #                 total_cpu += p.cpu_percent(interval=0)
            #                 total_mem += p.memory_info().rss / (1024 * 1024)
            #             else:
            #                 finished[i] = True
            #         except psutil.NoSuchProcess:
            #             finished[i] = True

            total_cpu = psutil.cpu_percent(interval=0)  # 主机总CPU使用率
            total_mem = psutil.virtual_memory().used / (1024 * 1024)  # 主机已用内存

            # 打印并写入CSV
            print(f"时间：{current_time:.3f}s | CPU：{total_cpu:.1f}% | 内存：{total_mem:.1f}MB")
            writer.writerow([round(current_time, 3), round(total_cpu, 1), round(total_mem, 1)])

            # 基准监控时：持续采集30秒（可调整），避免无限循环
            if is_benchmark and current_time >= 30:
                print("基准监控结束（已采集30秒）")
                break

            await asyncio.sleep(MONITOR_INTERVAL)

async def main():
    if AGENT_COUNT < 0:
        raise ValueError("AGENT_COUNT 不能为负数，请设置为 0 或正整数")

    # 场景1：AGENT_COUNT=0 → 基准监控（采集主机空闲指标）
    if AGENT_COUNT == 0:
        print(f"AGENT_COUNT=0，开始采集主机基准指标（持续30秒）...")
        await monitor_procs(procs=[], is_benchmark=True)
        print(f"基准指标已保存到：{OUTPUT_CSV}")
        return

    # 场景2：AGENT_COUNT>0 → 启动Agent并监控
    print(f"启动 {AGENT_COUNT} 个Agent进程...")
    procs = await asyncio.gather(*[run_agent(i) for i in range(AGENT_COUNT)])
    print(f"所有Agent启动完成，开始监控资源...")

    # 启动监控任务
    monitor_task = asyncio.create_task(monitor_procs(procs))

    # 等待所有Agent完成
    await asyncio.gather(*[p.wait() for p in procs])
    print("所有Agent任务执行完毕，等待最后一次监控...")

    # 等待监控任务结束
    await monitor_task
    print(f"监控数据已保存到：{OUTPUT_CSV}")

if __name__ == "__main__":
    asyncio.run(main())
