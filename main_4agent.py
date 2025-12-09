import argparse
import asyncio
import os

from app.agent.manus import Manus
from app.logger import logger


async def main():
    # 创建并初始化四个 Manus agent
    agent1 = await Manus.create()
    agent2 = await Manus.create()
    agent3 = await Manus.create()
    agent4 = await Manus.create()
    logger.info("[Profiling] Created four Manus agents.")

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
        logger.warning("Processing your request with four agents...")

        # 同时运行四个 agent（使用相同的 prompt）
        await asyncio.gather(
            agent1.run(prompt),
            agent2.run(prompt),
            agent3.run(prompt),
            agent4.run(prompt)
        )
        logger.info("Request processing completed for all four agents.")
    except KeyboardInterrupt:
        logger.warning("Operation interrupted.")
    finally:
        # 确保四个 agent 的资源都被清理
        await asyncio.gather(
            agent1.cleanup(),
            agent2.cleanup(),
            agent3.cleanup(),
            agent4.cleanup(),
            return_exceptions=True  # 即使一个失败也继续清理其他的
        )

    # 强制退出，避免任何未完成的任务阻止进程退出
    logger.info("[Profiling] Force exiting process...")
    os._exit(0)

if __name__ == "__main__":
    logger.info("[Profiling] Starting main_4agent.py execution")
    asyncio.run(main())

