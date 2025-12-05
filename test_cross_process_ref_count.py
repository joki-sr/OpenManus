#!/usr/bin/env python3
"""
测试跨进程引用计数同步（乐观锁方案）
"""
import asyncio
import json
import time
from pathlib import Path
from app.sandbox.client import create_shared_sandbox_client
from app.sandbox.core.shared_pool import get_shared_pool

async def test_cross_process_ref_count():
    """测试跨进程引用计数的正确性"""
    print("=" * 60)
    print("测试跨进程引用计数同步（乐观锁方案）")
    print("=" * 60)

    # 清理注册表
    registry_dir = Path("/tmp/openmanus_sandbox_registry")
    if registry_dir.exists():
        for f in registry_dir.glob("test_ref_count_*.json"):
            f.unlink()

    tag = "test_ref_count"

    # 获取pool实例并设置配置
    pool = get_shared_pool()
    original_max_sandboxes = pool.max_sandboxes_per_tag
    original_max_concurrency = pool.max_concurrency_per_sandbox

    pool.max_sandboxes_per_tag = 5
    pool.max_concurrency_per_sandbox = 3  # 每个sandbox最多3个并发引用

    print(f"\n配置:")
    print(f"  max_sandboxes_per_tag={pool.max_sandboxes_per_tag}")
    print(f"  max_concurrency_per_sandbox={pool.max_concurrency_per_sandbox}")
    print(f"\n创建多个客户端，测试跨进程引用计数...\n")

    # 创建多个客户端，模拟多个进程
    clients = []
    sandbox_ids = set()

    print("步骤1: 创建5个客户端（max_concurrency_per_sandbox=3，应该创建2个sandbox）")
    for i in range(5):
        client = create_shared_sandbox_client(tag=tag)
        clients.append(client)
        await client.create()
        sandbox_ids.add(client.sandbox_id)
        print(f"  客户端 {i+1}: sandbox_id={client.sandbox_id[:12]}...")
        await asyncio.sleep(0.1)  # 等待异步更新

    print(f"\n实际创建的sandbox数量: {len(sandbox_ids)}")
    print(f"预期: 由于max_concurrency_per_sandbox=3，前3个客户端使用第1个sandbox，")
    print(f"      第4、5个客户端应该创建第2个sandbox")

    # 等待异步更新完成
    await asyncio.sleep(0.5)

    # 检查注册表中的引用计数
    print("\n步骤2: 检查注册表中的引用计数")
    registry_files = list(registry_dir.glob(f"{tag}_*.json"))
    for registry_file in sorted(registry_files):
        with open(registry_file, 'r') as f:
            data = json.load(f)
        sandbox_id_short = data.get('sandbox_id', '')[:12] if data.get('sandbox_id') else ''
        print(f"  {sandbox_id_short}...:")
        print(f"    ref_count={data.get('ref_count', 0)}")
        print(f"    version={data.get('version', 0)}")

    # 测试max_concurrency_per_sandbox限制
    print("\n步骤3: 测试max_concurrency_per_sandbox限制")
    print("  尝试创建更多客户端（应该创建新的sandbox，因为已有2个sandbox各被3个和2个客户端引用）")

    extra_clients = []
    initial_sandbox_count = len(sandbox_ids)
    for i in range(3):
        try:
            client = create_shared_sandbox_client(tag=tag)
            extra_clients.append(client)
            await client.create()
            sandbox_ids.add(client.sandbox_id)
            print(f"  额外客户端 {i+1}: sandbox_id={client.sandbox_id[:12]}...")
            await asyncio.sleep(0.2)  # 等待异步更新
        except Exception as e:
            print(f"  额外客户端 {i+1} 创建失败: {e}")

    print(f"\n  创建额外客户端后，sandbox数量: {len(sandbox_ids)} (之前: {initial_sandbox_count})")

    # 再次检查注册表（重新获取，包含新创建的sandbox）
    await asyncio.sleep(0.5)
    print("\n步骤4: 检查达到限制后的引用计数")
    registry_files = list(registry_dir.glob(f"{tag}_*.json"))  # 重新获取，包含新创建的
    for registry_file in sorted(registry_files):
        with open(registry_file, 'r') as f:
            data = json.load(f)
        sandbox_id_short = data.get('sandbox_id', '')[:12] if data.get('sandbox_id') else ''
        print(f"  {sandbox_id_short}...: ref_count={data.get('ref_count', 0)}, version={data.get('version', 0)}")

    # 释放部分客户端
    print("\n步骤5: 释放前3个客户端")
    for i in range(3):
        await clients[i].cleanup()
        print(f"  已释放客户端 {i+1}")
        await asyncio.sleep(0.2)  # 等待异步更新

    # 检查释放后的引用计数
    await asyncio.sleep(0.5)
    print("\n步骤6: 检查释放后的引用计数")
    registry_files = list(registry_dir.glob(f"{tag}_*.json"))  # 重新获取
    for registry_file in sorted(registry_files):
        with open(registry_file, 'r') as f:
            data = json.load(f)
        sandbox_id_short = data.get('sandbox_id', '')[:12] if data.get('sandbox_id') else ''
        print(f"  {sandbox_id_short}...: ref_count={data.get('ref_count', 0)}, version={data.get('version', 0)}")

    # 释放所有客户端
    print("\n步骤7: 释放所有剩余客户端")
    for i in range(3, len(clients)):
        await clients[i].cleanup()
        print(f"  已释放客户端 {i+1}")

    for client in extra_clients:
        try:
            await client.cleanup()
        except:
            pass

    # 最终检查
    await asyncio.sleep(0.5)
    print("\n步骤8: 最终检查注册表")
    registry_files = list(registry_dir.glob(f"{tag}_*.json"))  # 重新获取
    if registry_files:
        for registry_file in sorted(registry_files):
            if registry_file.exists():
                with open(registry_file, 'r') as f:
                    data = json.load(f)
                sandbox_id_short = data.get('sandbox_id', '')[:12] if data.get('sandbox_id') else ''
                print(f"  {sandbox_id_short}...: ref_count={data.get('ref_count', 0)}, version={data.get('version', 0)}")
    else:
        print("  所有sandbox已被清理（注册表为空）")

    # 恢复原始配置
    pool.max_sandboxes_per_tag = original_max_sandboxes
    pool.max_concurrency_per_sandbox = original_max_concurrency

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_cross_process_ref_count())
