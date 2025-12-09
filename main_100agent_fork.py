import argparse
import asyncio
import multiprocessing
import os
import psutil
import signal
import sys

# ========== 主进程预加载环境 ==========
# 在主进程中导入所有需要的库，这样 fork 后的子进程可以共享这些已加载的库
from app.agent.manus import Manus
from app.logger import logger

# 可以在这里预加载其他需要共享的资源
# 例如：模型、配置文件等


# ========== 子进程工作函数 ==========
async def run_single_agent(agent_id: int, prompt: str, cpu_core: int):
    """在子进程中运行单个 agent"""
    try:
        # 绑定到指定的 CPU 核心
        try:
            p = psutil.Process(os.getpid())
            p.cpu_affinity([cpu_core])
            logger.info(f"[Agent {agent_id}] Bound to CPU core {cpu_core} (PID: {os.getpid()})")
        except Exception as e:
            logger.warning(f"[Agent {agent_id}] Failed to bind to core {cpu_core}: {e}")

        # 创建并运行 agent（使用共享的已加载环境）
        agent = await Manus.create()
        logger.info(f"[Agent {agent_id}] Created agent.")

        await agent.run(prompt)
        logger.info(f"[Agent {agent_id}] Completed.")

        await agent.cleanup()
    except Exception as e:
        logger.error(f"[Agent {agent_id}] Error: {e}", exc_info=True)
    finally:
        os._exit(0)


def worker_process(agent_id: int, prompt: str, cpu_core: int):
    """工作进程入口函数（在子进程中执行）"""
    # 设置信号处理，确保子进程可以正常退出
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    # 运行异步 agent
    asyncio.run(run_single_agent(agent_id, prompt, cpu_core))


# ========== 主进程函数 ==========
def main():
    NUM_AGENTS = 100

    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Run Manus agent with a prompt (fork mode)")
    parser.add_argument(
        "--prompt", type=str, required=False, help="Input prompt for the agent"
    )
    args = parser.parse_args()

    # 获取 prompt
    prompt = args.prompt if args.prompt else input("Enter your prompt: ")
    if not prompt.strip():
        logger.warning("Empty prompt provided.")
        return

    logger.info("[Profiling] Starting main_100agent_fork.py execution")
    logger.info(f"[Profiling] Environment pre-loaded (shared libraries ready)")
    logger.info(f"[Profiling] Will fork {NUM_AGENTS} child processes")

    # 获取 CPU 核心数
    cpu_count = psutil.cpu_count(logical=True)
    logger.info(f"[Profiling] Available CPU cores: {cpu_count}")

    # 创建进程列表
    processes = []

    try:
        # Fork 100 个子进程
        for i in range(NUM_AGENTS):
            cpu_core = i % cpu_count  # 循环分配到不同核心

            # 创建子进程（使用 fork）
            p = multiprocessing.Process(
                target=worker_process,
                args=(i, prompt, cpu_core),
                name=f"Agent-{i}"
            )
            p.start()
            processes.append(p)

            if (i + 1) % 10 == 0:
                logger.info(f"[Profiling] Forked {i + 1}/{NUM_AGENTS} processes...")

        logger.info(f"[Profiling] All {NUM_AGENTS} processes forked. Waiting for completion...")

        # 等待所有子进程完成
        for i, p in enumerate(processes):
            p.join()
            if (i + 1) % 10 == 0:
                logger.info(f"[Profiling] Completed {i + 1}/{NUM_AGENTS} processes...")

        logger.info(f"[Profiling] All {NUM_AGENTS} agent processes completed.")

    except KeyboardInterrupt:
        logger.warning("[Profiling] Interrupted. Terminating all child processes...")
        for p in processes:
            if p.is_alive():
                p.terminate()
        for p in processes:
            p.join(timeout=5)
            if p.is_alive():
                p.kill()
    except Exception as e:
        logger.error(f"[Profiling] Error: {e}", exc_info=True)
        # 清理所有子进程
        for p in processes:
            if p.is_alive():
                p.terminate()
        for p in processes:
            p.join(timeout=5)
            if p.is_alive():
                p.kill()


if __name__ == "__main__":
    # 确保使用 fork 模式（Linux 默认）
    if sys.platform != 'win32':
        try:
            multiprocessing.set_start_method('fork', force=True)
        except RuntimeError:
            # 如果已经设置过，忽略错误
            pass

    # 运行主函数
    main()

