"""
共享Sandbox使用示例

展示如何在agent和tool中使用共享sandbox功能。
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径，以便直接运行此脚本
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.sandbox.client import create_shared_sandbox_client
from app.sandbox.core.shared_pool import get_shared_pool
from app.config import SandboxSettings
from app.logger import logger



async def example_agent_with_shared_sandbox():
    """示例：Agent使用共享sandbox"""
    # 创建共享sandbox client，指定功能类型
    # 多个使用相同tag的agent会共享同一个sandbox
    sandbox_client = create_shared_sandbox_client(tag="python_execute")

    try:
        # 获取或创建共享sandbox
        await sandbox_client.create()

        # 执行任务
        output = await sandbox_client.run_command("python --version")
        print(f"Python version: {output}")

        # 写入文件
        await sandbox_client.write_file("/workspace/test.py", "print('Hello from shared sandbox!')")

        # 执行Python代码
        result = await sandbox_client.run_command("python /workspace/test.py")
        print(f"Execution result: {result}")

    finally:
        # 释放sandbox引用（不会立即销毁，只是减少引用计数并解除对sandbox的引用）
        await sandbox_client.cleanup()


async def example_multiple_agents_sharing():
    """示例：多个agent共享同一个sandbox"""
    pool = get_shared_pool()

    async def agent_task(agent_id: int):
        """模拟一个agent任务"""
        logger.info(f"[Example] Agent {agent_id}: Starting...")
        client = create_shared_sandbox_client(tag="python_execute")
        try:
            # 显示获取前的状态
            stats_before = pool.get_stats()
            logger.info(f"[Example] Agent {agent_id}: Pool stats before acquire: {stats_before['pools_by_tag']}")

            await client.create()
            print(f"Agent {agent_id}: Acquired sandbox (ID: {client.sandbox_id[:12]}...)")

            # 显示获取后的状态
            stats_after = pool.get_stats()
            logger.info(f"[Example] Agent {agent_id}: Pool stats after acquire: {stats_after['pools_by_tag']}")
            logger.info(f"[Example] Agent {agent_id}: Ref count for sandbox: {stats_after['ref_counts'].get(client.sandbox_id, 'N/A')}")

            # 执行任务
            result = await client.run_command(f"echo 'Agent {agent_id} is working'")
            logger.info(f"[Example] Agent {agent_id}: Command result: {result.strip()}")
            await asyncio.sleep(0.5)  # 模拟任务执行

            print(f"Agent {agent_id}: Releasing sandbox")
        finally:
            await client.cleanup()
            # 显示释放后的状态
            stats_released = pool.get_stats()
            logger.info(f"[Example] Agent {agent_id}: Pool stats after release: {stats_released['pools_by_tag']}")

    # 并发运行多个agent
    logger.info("[Example] Starting 3 concurrent agents...")
    tasks = [agent_task(i) for i in range(3)]
    await asyncio.gather(*tasks)

    # 显示最终状态
    final_stats = pool.get_stats()
    print("\n=== Final Pool Statistics ===")
    print(f"Total sandboxes: {final_stats['total_sandboxes']}")
    print(f"Pools by tag: {final_stats['pools_by_tag']}")
    print(f"Reference counts: {final_stats['ref_counts']}")
    print("All agents completed")


async def example_different_tags():
    """示例：不同tag的sandbox是隔离的"""
    pool = get_shared_pool()

    # Python执行sandbox
    logger.info("[Example] Creating Python execution sandbox...")
    python_client = create_shared_sandbox_client(tag="python_execute")
    await python_client.create()
    print(f"Python sandbox ID: {python_client.sandbox_id[:12]}...")
    await python_client.write_file("/workspace/python_file.py", "print('Python')")
    content = await python_client.read_file("/workspace/python_file.py")
    print(f"Written content: {content}")
    await python_client.cleanup()

    # 文件操作sandbox（不同的tag，不同的sandbox）
    logger.info("[Example] Creating file operations sandbox...")
    file_client = create_shared_sandbox_client(tag="file_ops")
    await file_client.create()
    print(f"File ops sandbox ID: {file_client.sandbox_id[:12]}...")
    await file_client.write_file("/workspace/file.txt", "File content")
    content = await file_client.read_file("/workspace/file.txt")
    print(f"Written content: {content}")
    await file_client.cleanup()

    # 验证不同tag使用不同的sandbox
    stats = pool.get_stats()
    print(f"\nDifferent tags use different sandboxes: {stats['pools_by_tag']}")


async def example_with_custom_config():
    """示例：使用自定义配置创建共享sandbox"""
    logger.info("[Example] Creating sandbox with custom config...")
    config = SandboxSettings(
        image="python:3.12-slim",
        memory_limit="1g",
        cpu_limit=2.0,
        timeout=600,
    )

    client = create_shared_sandbox_client(tag="data_analysis")
    try:
        await client.create(config=config)
        print(f"Custom config sandbox ID: {client.sandbox_id[:12]}...")
        # 验证配置
        result = await client.run_command("python --version")
        print(f"Sandbox Python version: {result.strip()}")
    finally:
        await client.cleanup()


async def example_pool_stats():
    """示例：查看共享池统计信息"""
    pool = get_shared_pool()

    print("=== Initial Pool Statistics ===")
    initial_stats = pool.get_stats()
    print(f"Total sandboxes: {initial_stats['total_sandboxes']}")
    print(f"Pools by tag: {initial_stats['pools_by_tag']}")

    # 创建一些sandbox
    logger.info("[Example] Creating sandboxes...")
    client1 = create_shared_sandbox_client(tag="python_execute")
    await client1.create()
    print(f"Client 1 sandbox ID: {client1.sandbox_id[:12]}...")

    client2 = create_shared_sandbox_client(tag="file_ops")
    await client2.create()
    print(f"Client 2 sandbox ID: {client2.sandbox_id[:12]}...")

    # 查看统计信息
    print("\n=== After Creating Sandboxes ===")
    stats = pool.get_stats()
    print(f"Total sandboxes: {stats['total_sandboxes']}")
    print(f"Pools by tag: {stats['pools_by_tag']}")
    print(f"Reference counts: {stats['ref_counts']}")

    # 清理
    logger.info("[Example] Releasing sandboxes...")
    await client1.cleanup()
    await client2.cleanup()

    print("\n=== After Cleanup ===")
    final_stats = pool.get_stats()
    print(f"Total sandboxes: {final_stats['total_sandboxes']}")
    print(f"Pools by tag: {final_stats['pools_by_tag']}")
    print(f"Reference counts: {final_stats['ref_counts']}")
    print("(Note: Sandboxes will be cleaned up after idle timeout)")


async def example_high_concurrency_python_execute(agent_count: int = 100):
    """示例：验证单个tag在高并发场景下的行为。"""
    pool = get_shared_pool()

    async def agent_task(agent_id: int) -> str:
        client = create_shared_sandbox_client(tag="python_execute")
        try:
            await client.create()
            # 在共享sandbox中执行简单python命令
            return await client.run_command(
                f"python -c \"print('agent {agent_id} ok')\""
            )
        finally:
            await client.cleanup()

    print(f"[HighConcurrency] Launching {agent_count} concurrent agents...")
    stats_before = pool.get_stats()
    print(f"[HighConcurrency] Pool stats before: {stats_before}")

    results = await asyncio.gather(
        *(agent_task(i) for i in range(agent_count))
    )

    stats_after = pool.get_stats()
    print(f"[HighConcurrency] Pool stats after: {stats_after}")
    print(f"[HighConcurrency] Sample outputs: {results[:3]} ...")


if __name__ == "__main__":
    # print("=== Example 1: Basic usage ===")
    # asyncio.run(example_agent_with_shared_sandbox())

    print("\n=== Example 2: Multiple agents sharing ===")
    asyncio.run(example_multiple_agents_sharing())

    # print("\n=== Example 6: High concurrency python_execute ===")
    # asyncio.run(example_high_concurrency_python_execute(agent_count=100))

    # print("\n=== Example 3: Different tags ===")
    # asyncio.run(example_different_tags())

    # print("\n=== Example 4: Custom config ===")
    # asyncio.run(example_with_custom_config())

    # print("\n=== Example 5: Pool statistics ===")
    # asyncio.run(example_pool_stats())

