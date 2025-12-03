"""
共享Sandbox使用示例 - 顺序执行版本（便于调试）

这是example_usage.py的顺序执行版本，所有操作按顺序执行，便于观察和调试。
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.sandbox.client import create_shared_sandbox_client
from app.sandbox.core.shared_pool import get_shared_pool
from app.config import SandboxSettings
from app.logger import logger


async def example_multiple_agents_sequential():
    """示例：多个agent顺序执行（便于调试观察）"""
    pool = get_shared_pool()

    print("=" * 60)
    print("Example: Multiple Agents Sharing Sandbox (Sequential)")
    print("=" * 60)

    async def agent_task(agent_id: int):
        """模拟一个agent任务"""
        print(f"\n--- Agent {agent_id} Starting ---")

        # 显示当前池状态
        stats = pool.get_stats()
        print(f"Pool status before Agent {agent_id}:")
        print(f"  Total sandboxes: {stats['total_sandboxes']}")
        print(f"  Pools by tag: {stats['pools_by_tag']}")
        print(f"  Reference counts: {stats['ref_counts']}")

        client = create_shared_sandbox_client(tag="python_execute")
        try:
            print(f"Agent {agent_id}: Acquiring sandbox...")
            await client.create()
            print(f"Agent {agent_id}: Acquired sandbox (ID: {client.sandbox_id[:12]}...)")

            # 显示获取后的状态
            stats = pool.get_stats()
            ref_count = stats['ref_counts'].get(client.sandbox_id, 0)
            print(f"Agent {agent_id}: Sandbox ref_count = {ref_count}")

            # 执行任务
            print(f"Agent {agent_id}: Executing command...")
            result = await client.run_command(f"echo 'Agent {agent_id} is working'")
            print(f"Agent {agent_id}: Command result: {result.strip()}")

            await asyncio.sleep(0.5)  # 模拟任务执行

            print(f"Agent {agent_id}: Releasing sandbox...")
        finally:
            await client.cleanup()
            stats = pool.get_stats()
            ref_count = stats['ref_counts'].get(client.sandbox_id, 0) if client.sandbox_id else 0
            print(f"Agent {agent_id}: Released (ref_count = {ref_count})")
            print(f"--- Agent {agent_id} Completed ---")

    # 顺序执行（而不是并发）
    print("\n>>> Executing agents sequentially for easier debugging...\n")
    for i in range(3):
        await agent_task(i)
        await asyncio.sleep(0.2)  # 短暂延迟，便于观察

    # 显示最终状态
    print("\n" + "=" * 60)
    print("Final Pool Statistics:")
    final_stats = pool.get_stats()
    print(f"  Total sandboxes: {final_stats['total_sandboxes']}")
    print(f"  Pools by tag: {final_stats['pools_by_tag']}")
    print(f"  Reference counts: {final_stats['ref_counts']}")
    print("=" * 60)


async def example_reuse_sandbox():
    """示例：演示sandbox复用"""
    pool = get_shared_pool()

    print("\n" + "=" * 60)
    print("Example: Sandbox Reuse")
    print("=" * 60)

    # 第一次获取
    print("\n>>> First acquisition:")
    client1 = create_shared_sandbox_client(tag="python_execute")
    await client1.create()
    sandbox_id_1 = client1.sandbox_id
    print(f"Sandbox ID: {sandbox_id_1[:12]}...")
    stats = pool.get_stats()
    print(f"Ref count: {stats['ref_counts'].get(sandbox_id_1, 0)}")

    # 释放
    print("\n>>> Releasing...")
    await client1.cleanup()
    stats = pool.get_stats()
    print(f"Ref count after release: {stats['ref_counts'].get(sandbox_id_1, 0)}")

    # 第二次获取（应该复用同一个）
    print("\n>>> Second acquisition (should reuse):")
    client2 = create_shared_sandbox_client(tag="python_execute")
    await client2.create()
    sandbox_id_2 = client2.sandbox_id
    print(f"Sandbox ID: {sandbox_id_2[:12]}...")
    stats = pool.get_stats()
    print(f"Ref count: {stats['ref_counts'].get(sandbox_id_2, 0)}")

    if sandbox_id_1 == sandbox_id_2:
        print("✓ SUCCESS: Reused the same sandbox!")
    else:
        print("✗ Different sandbox (might be timing issue)")

    await client2.cleanup()
    print("=" * 60)


if __name__ == "__main__":
    print("Running sequential examples for easier debugging...\n")

    asyncio.run(example_multiple_agents_sequential())
    asyncio.run(example_reuse_sandbox())


