#!/usr/bin/env python3
"""
调试版本的main.py，添加详细的退出检查
"""
import argparse
import asyncio
import sys
import traceback
import threading
import psutil
import os

from app.agent.manus import Manus
from app.logger import logger

def debug_exit_state():
    """在退出前检查进程状态"""
    current_process = psutil.Process(os.getpid())

    logger.info("=== 退出前状态检查 ===")
    logger.info(f"线程数: {current_process.num_threads()}")
    logger.info(f"打开的文件数: {len(current_process.open_files())}")
    logger.info(f"连接数: {len(current_process.connections())}")

    # 检查所有线程
    threads = threading.enumerate()
    logger.info(f"活跃线程数: {len(threads)}")
    for thread in threads:
        logger.info(f"  - {thread.name}: alive={thread.is_alive()}, daemon={thread.daemon}")

    # 检查asyncio任务
    try:
        loop = asyncio.get_running_loop()
        tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
        logger.info(f"未完成的asyncio任务数: {len(tasks)}")
        for task in tasks:
            logger.info(f"  - {task.get_name()}: {task}")
            try:
                stack = task.get_stack()
                if stack:
                    logger.info(f"    堆栈: {''.join(traceback.format_stack(stack[0]))}")
            except:
                pass
    except RuntimeError:
        logger.info("没有运行中的事件循环")


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
    except Exception as e:
        logger.error(f"Error during execution: {e}", exc_info=True)
    finally:
        # Ensure agent resources are cleaned up before exiting
        logger.info("Starting cleanup...")
        try:
            await agent.cleanup()
            logger.info("Agent cleanup completed.")
        except Exception as e:
            logger.error(f"Error during agent cleanup: {e}", exc_info=True)

        # 调试：检查退出前状态
        debug_exit_state()

        # 检查事件循环
        try:
            loop = asyncio.get_running_loop()
            tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
            if tasks:
                logger.warning(f"仍有 {len(tasks)} 个未完成的任务，等待5秒...")
                await asyncio.sleep(5)
                tasks_after = [t for t in asyncio.all_tasks(loop) if not t.done()]
                if tasks_after:
                    logger.error(f"5秒后仍有 {len(tasks_after)} 个未完成的任务:")
                    for task in tasks_after:
                        logger.error(f"  - {task.get_name()}: {task}")
        except RuntimeError:
            pass

        logger.info("Main function completed, exiting...")


if __name__ == "__main__":
    logger.info("[Profiling] Starting main.py execution")
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Process exiting...")

