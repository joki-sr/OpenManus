import argparse
import asyncio
import os

from app.agent.manus import Manus
from app.logger import logger


async def main():
    # 创建并初始化一百个 Manus agent
    NUM_AGENTS = 100
    logger.info(f"[Profiling] Creating {NUM_AGENTS} Manus agents...")
    agents = await asyncio.gather(*[Manus.create() for _ in range(NUM_AGENTS)])
    logger.info(f"[Profiling] Created {NUM_AGENTS} Manus agents.")

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run Manus agent with a prompt")
    parser.add_argument(
        "--prompt", type=str, required=False, help="Input prompt for the agent"
    )
    args = parser.parse_args()
    logger.info("[Profiling] Parsed command line arguments.")

    try:
        # Use command line prompt if provided, otherwise ask for input
        prompt = args.prompt if args.prompt else input("Enter your prompt: ")
        if not prompt.strip():
            logger.warning("Empty prompt provided.")
            return
        logger.info("[Profiling] Parsed prompt.")
        logger.warning(f"Processing your request with {NUM_AGENTS} agents...")

        # 同时运行所有 agent（使用相同的 prompt）
        await asyncio.gather(*[agent.run(prompt) for agent in agents])
        logger.info(f"Request processing completed for all {NUM_AGENTS} agents.")
    except KeyboardInterrupt:
        logger.warning("Operation interrupted.")
    finally:
        # 确保所有 agent 的资源都被清理
        await asyncio.gather(
            *[agent.cleanup() for agent in agents],
            return_exceptions=True  # 即使一个失败也继续清理其他的
        )

    # 强制退出，避免任何未完成的任务阻止进程退出
    logger.info("[Profiling] Force exiting process...")
    os._exit(0)

if __name__ == "__main__":
    logger.info("[Profiling] Starting main_100agent.py execution")
    asyncio.run(main())

