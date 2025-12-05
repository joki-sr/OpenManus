#!/usr/bin/env python3
"""
验证sandbox配置是否生效的测试脚本

测试内容：
1. CPU限制：验证每个container的CPU core限制是否正确
   - 检查Docker容器的cpu_quota和cpu_period配置
   - 验证实际CPU限制是否匹配配置值

2. max_sandboxes_per_tag：验证同tag的sandbox数量限制
   - 设置较小的限制值（如2）
   - 尝试创建超过限制数量的sandbox
   - 验证是否在达到限制时抛出错误

3. max_concurrency_per_sandbox：验证每个sandbox的并发引用限制
   - 设置较小的限制值（如2）
   - 创建多个client引用同一个sandbox
   - 验证达到限制后是否创建新的sandbox

4. 运行时CPU使用：验证运行时CPU使用是否受限制
   - 运行CPU密集型任务
   - 检查Docker stats中的CPU使用率

使用方法：
    python test_sandbox_config.py
"""
import asyncio
import docker
from app.sandbox.client import create_shared_sandbox_client
from app.sandbox.core.shared_pool import get_shared_pool
from app.config import SandboxSettings
from app.logger import logger


async def test_cpu_limit():
    """测试CPU限制是否生效"""
    print("\n" + "="*60)
    print("测试1: CPU限制验证")
    print("="*60)

    # 创建不同CPU限制的sandbox
    test_configs = [
        SandboxSettings(cpu_limit=0.5, timeout=10),  # 0.5 core
        SandboxSettings(cpu_limit=1.0, timeout=10),  # 1.0 core
        SandboxSettings(cpu_limit=2.0, timeout=10),  # 2.0 core
    ]

    docker_client = docker.from_env()
    containers_info = []

    for config in test_configs:
        client = create_shared_sandbox_client(tag=f"test_cpu_{config.cpu_limit}")
        await client.create(config=config)

        # 获取container ID
        container_id = client.sandbox.container.id if client.sandbox else None
        if container_id:
            container = docker_client.containers.get(container_id)
            container.reload()

            # 读取Docker容器的CPU限制
            host_config = container.attrs.get('HostConfig', {})
            cpu_quota = host_config.get('CpuQuota', 0)
            cpu_period = host_config.get('CpuPeriod', 100000)

            actual_cpu = cpu_quota / cpu_period if cpu_period > 0 else 0
            expected_cpu = config.cpu_limit

            containers_info.append({
                'config_cpu': expected_cpu,
                'actual_cpu': actual_cpu,
                'cpu_quota': cpu_quota,
                'cpu_period': cpu_period,
                'container_id': container_id[:12],
            })

            print(f"配置CPU: {expected_cpu:.1f} core")
            print(f"  实际CPU: {actual_cpu:.2f} core (quota={cpu_quota}, period={cpu_period})")
            print(f"  容器ID: {container_id[:12]}")

            if abs(actual_cpu - expected_cpu) < 0.01:
                print(f"  ✓ CPU限制正确")
            else:
                print(f"  ✗ CPU限制不匹配！期望{expected_cpu}，实际{actual_cpu}")

        await client.cleanup()

    return containers_info


async def test_max_sandboxes_per_tag():
    """测试max_sandboxes_per_tag限制"""
    print("\n" + "="*60)
    print("测试2: max_sandboxes_per_tag限制验证")
    print("="*60)

    # 获取pool实例并设置较小的限制用于测试
    pool = get_shared_pool()
    original_max = pool.max_sandboxes_per_tag
    original_concurrency = pool.max_concurrency_per_sandbox

    # 临时设置为2进行测试，并设置并发限制为1，强制每个client创建新sandbox
    test_tag = "test_max_sandboxes"
    pool.max_sandboxes_per_tag = 2
    pool.max_concurrency_per_sandbox = 1  # 每个sandbox只能被1个client引用，强制创建新的

    print(f"设置 max_sandboxes_per_tag = {pool.max_sandboxes_per_tag}")
    print(f"设置 max_concurrency_per_sandbox = {pool.max_concurrency_per_sandbox} (强制创建新sandbox)")
    print(f"测试tag: {test_tag}")

    clients = []
    created_count = 0
    failed_count = 0
    sandbox_ids = set()

    try:
        # 尝试创建3个sandbox（超过限制）
        for i in range(3):
            try:
                client = create_shared_sandbox_client(tag=test_tag)
                await client.create()
                clients.append(client)
                sandbox_ids.add(client.sandbox_id)
                created_count += 1
                print(f"  ✓ 成功创建第 {created_count} 个sandbox: {client.sandbox_id[:12]}")
                print(f"    当前该tag的sandbox数量: {len(sandbox_ids)}")
            except RuntimeError as e:
                if "Maximum number of sandboxes" in str(e):
                    failed_count += 1
                    print(f"  ✗ 第 {i+1} 个sandbox创建失败（达到限制）: {e}")
                else:
                    raise

        print(f"\n结果: 成功创建 {created_count} 个，失败 {failed_count} 个")
        print(f"实际创建的sandbox数量: {len(sandbox_ids)}")

        if len(sandbox_ids) == 2 and failed_count == 1:
            print("  ✓ max_sandboxes_per_tag限制生效")
        elif len(sandbox_ids) == 2 and failed_count == 0:
            print("  ⚠ 创建了2个sandbox，但第3个没有抛出错误（可能逻辑有延迟）")
        else:
            print(f"  ✗ 限制未生效！期望创建2个不同的sandbox失败1个，实际创建{len(sandbox_ids)}个不同的sandbox失败{failed_count}个")

    finally:
        # 清理
        for client in clients:
            await client.cleanup()

        # 恢复原始值
        pool.max_sandboxes_per_tag = original_max
        pool.max_concurrency_per_sandbox = original_concurrency


async def test_max_concurrency_per_sandbox():
    """测试max_concurrency_per_sandbox限制"""
    print("\n" + "="*60)
    print("测试3: max_concurrency_per_sandbox限制验证")
    print("="*60)

    pool = get_shared_pool()
    original_max = pool.max_concurrency_per_sandbox

    # 临时设置为2进行测试
    test_tag = "test_concurrency"
    pool.max_concurrency_per_sandbox = 2

    print(f"设置 max_concurrency_per_sandbox = {pool.max_concurrency_per_sandbox}")
    print(f"测试tag: {test_tag}")

    clients = []

    try:
        # 创建第一个client并acquire
        client1 = create_shared_sandbox_client(tag=test_tag)
        await client1.create()
        sandbox_id_1 = client1.sandbox_id
        clients.append(client1)
        ref_count_1 = pool._ref_counts.get(sandbox_id_1, 0)
        print(f"  ✓ Client 1 acquire sandbox: {sandbox_id_1[:12]}")
        print(f"    当前引用计数: {ref_count_1}")

        # 创建第二个client，应该复用同一个sandbox
        client2 = create_shared_sandbox_client(tag=test_tag)
        await client2.create()
        sandbox_id_2 = client2.sandbox_id
        clients.append(client2)
        ref_count_2 = pool._ref_counts.get(sandbox_id_2, 0)
        print(f"  ✓ Client 2 acquire sandbox: {sandbox_id_2[:12]}")
        print(f"    当前引用计数: {ref_count_2}")

        if sandbox_id_1 == sandbox_id_2:
            print(f"  ✓ 复用了同一个sandbox")
            if ref_count_2 == 2:
                print(f"  ✓ 引用计数正确（2）")
            else:
                print(f"  ✗ 引用计数不正确，期望2，实际{ref_count_2}")
        else:
            print(f"  ✗ 没有复用同一个sandbox")

        # 尝试创建第三个client，应该创建新的sandbox（因为达到并发限制）
        print(f"\n尝试创建Client 3（应该创建新sandbox，因为达到并发限制）...")
        client3 = create_shared_sandbox_client(tag=test_tag)
        await client3.create()
        sandbox_id_3 = client3.sandbox_id
        clients.append(client3)
        ref_count_3 = pool._ref_counts.get(sandbox_id_3, 0)
        print(f"  ✓ Client 3 acquire sandbox: {sandbox_id_3[:12]}")
        print(f"    当前引用计数: {ref_count_3}")

        # 检查Client 1和2的引用计数
        ref_count_1_after = pool._ref_counts.get(sandbox_id_1, 0)
        print(f"  Client 1的sandbox引用计数: {ref_count_1_after}")

        if sandbox_id_3 != sandbox_id_1:
            print(f"  ✓ 创建了新的sandbox（因为达到并发限制）")
            if ref_count_3 == 1:
                print(f"  ✓ 新sandbox引用计数正确（1）")
            else:
                print(f"  ✗ 新sandbox引用计数不正确，期望1，实际{ref_count_3}")
        else:
            print(f"  ✗ 仍然复用同一个sandbox（并发限制未生效）")
            print(f"    可能原因：跨进程加载时引用计数未正确累加")

        # 打印pool统计信息
        stats = pool.get_stats()
        print(f"\nPool统计信息:")
        print(f"  总sandbox数: {stats.get('total_sandboxes', 0)}")
        print(f"  按tag分组: {stats.get('pools_by_tag', {})}")
        print(f"  引用计数: {stats.get('ref_counts', {})}")

    finally:
        # 清理
        for client in clients:
            await client.cleanup()

        # 恢复原始值
        pool.max_concurrency_per_sandbox = original_max


async def test_actual_runtime_cpu():
    """测试运行时CPU使用是否受限制"""
    print("\n" + "="*60)
    print("测试4: 运行时CPU使用验证")
    print("="*60)

    # 创建CPU限制为0.5的sandbox
    config = SandboxSettings(cpu_limit=0.5, timeout=30)
    client = create_shared_sandbox_client(tag="test_runtime_cpu")
    await client.create(config=config)

    container_id = client.sandbox.container.id if client.sandbox else None
    if container_id:
        print(f"容器ID: {container_id[:12]}")
        print("运行CPU密集型任务（计算1到10000000的加和）...")

        # 运行CPU密集型任务
        code = """
import time
start = time.time()
sum_result = 0
for i in range(1, 10000001):
    sum_result += i
end = time.time()
print(f"计算结果: {sum_result}")
print(f"耗时: {end - start:.2f}秒")
"""

        result = await client.sandbox.run_command(f"python -c '{code}'", timeout=30)
        print(f"执行结果:\n{result}")

        # 注意：任务已经完成，stats获取的是完成后的状态，CPU使用率会很低
        # 要准确测试CPU限制，需要在任务运行期间监控
        print(f"\n注意：任务已完成，CPU使用率统计可能不准确")
        print(f"要验证CPU限制，建议使用 'docker stats {container_id[:12]}' 在任务运行期间监控")
        print(f"或者使用 'docker inspect {container_id[:12]}' 查看CPU配置")

        # 检查Docker容器的CPU配置
        docker_client = docker.from_env()
        container = docker_client.containers.get(container_id)
        container.reload()
        host_config = container.attrs.get('HostConfig', {})
        cpu_quota = host_config.get('CpuQuota', 0)
        cpu_period = host_config.get('CpuPeriod', 100000)
        actual_cpu = cpu_quota / cpu_period if cpu_period > 0 else 0
        print(f"容器CPU配置: {actual_cpu:.2f} core (quota={cpu_quota}, period={cpu_period})")
        print(f"配置限制: 0.5 core")

    await client.cleanup()


async def main():
    """运行所有测试"""
    print("开始验证sandbox配置...")

    try:
        # 测试1: CPU限制
        await test_cpu_limit()

        # 测试2: max_sandboxes_per_tag
        await test_max_sandboxes_per_tag()

        # 测试3: max_concurrency_per_sandbox
        await test_max_concurrency_per_sandbox()

        # 测试4: 运行时CPU使用
        await test_actual_runtime_cpu()

        print("\n" + "="*60)
        print("所有测试完成！")
        print("="*60)

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())

