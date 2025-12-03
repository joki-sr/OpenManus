import argparse
import asyncio
import os

from app.agent.manus import Manus
from app.logger import logger


async def main():
    # Create and initialize Manus agent
    agent = await Manus.create()
    logger.info("[Profiling] Created Manus agent.")

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
        logger.warning("Processing your request...")
        await agent.run(prompt)
        logger.info("Request processing completed.")
    except KeyboardInterrupt:
        logger.warning("Operation interrupted.")
    finally:
        # Ensure agent resources are cleaned up before exiting
        await agent.cleanup()

    # 强制退出，避免任何未完成的任务阻止进程退出
    logger.info("[Profiling] Force exiting process...")
    os._exit(0)

if __name__ == "__main__":
    logger.info("[Profiling] Starting main.py execution")
    asyncio.run(main())
