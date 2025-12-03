# 共享Sandbox使用指南

## 概述

共享Sandbox功能允许多个agent进程共享特定功能的sandbox实例，从而减少资源消耗和提高效率。

## 架构设计

### 核心组件

1. **SharedSandboxPool**: 管理按功能类型（tag）分组的sandbox池
2. **SharedSandboxClient**: 支持从共享池获取sandbox的client
3. **引用计数机制**: 跟踪每个sandbox的使用者数量
4. **自动清理**: 当引用计数为0且空闲超时后自动清理

### 工作流程

```
Agent进程1 (tag="python_execute")
    ↓
SharedSandboxPool.acquire_sandbox(tag="python_execute")
    ↓
创建或复用sandbox → ref_count=1
    ↓
执行任务
    ↓
SharedSandboxPool.release_sandbox() → ref_count=0
    ↓
空闲超时后自动清理

Agent进程2 (tag="python_execute")
    ↓
SharedSandboxPool.acquire_sandbox(tag="python_execute")
    ↓
复用同一个sandbox → ref_count=1
```

## 使用方法

### 方法1: 使用SharedSandboxClient（推荐）

```python
from app.sandbox.client import create_shared_sandbox_client

# 创建共享sandbox client，指定功能类型
sandbox_client = create_shared_sandbox_client(tag="python_execute")

# 获取或创建sandbox（如果池中已有相同tag的可用sandbox，会复用）
await sandbox_client.create()

# 使用sandbox执行任务
output = await sandbox_client.run_command("python --version")

# 释放sandbox引用（不会立即销毁，只是减少引用计数）
await sandbox_client.cleanup()
```

### 方法2: 直接使用SharedSandboxPool

```python
from app.sandbox.core.shared_pool import get_shared_pool

pool = get_shared_pool()

# 获取sandbox
sandbox_id = await pool.acquire_sandbox(tag="python_execute")
sandbox = await pool.get_sandbox(sandbox_id)

# 使用sandbox
output = await sandbox.run_command("python --version")

# 释放引用
await pool.release_sandbox(sandbox_id)
```

## 功能类型标签（Tag）

建议使用以下tag来区分不同功能的sandbox：

- `"python_execute"`: Python代码执行
- `"file_ops"`: 文件操作
- `"data_analysis"`: 数据分析
- `"web_scraping"`: 网页爬取
- `"default"`: 默认通用sandbox

## 配置参数

可以通过修改`SharedSandboxPool`的初始化参数来调整行为：

```python
from app.sandbox.core.shared_pool import SharedSandboxPool

pool = SharedSandboxPool(
    max_sandboxes_per_tag=5,  # 每个tag最多5个sandbox
    idle_timeout=3600,         # 空闲1小时后清理
    cleanup_interval=300,      # 每5分钟检查一次
)
```

## 在Agent中使用

### 修改Agent代码以支持共享sandbox

```python
from app.sandbox.client import create_shared_sandbox_client

class MyAgent(BaseAgent):
    def __init__(self, sandbox_tag: str = "default"):
        super().__init__()
        # 使用共享sandbox client
        self.sandbox_client = create_shared_sandbox_client(tag=sandbox_tag)

    async def run(self, request: str) -> str:
        # 获取共享sandbox
        await self.sandbox_client.create()

        try:
            # 执行任务...
            result = await self.sandbox_client.run_command("...")
        finally:
            # 释放sandbox引用
            await self.sandbox_client.cleanup()

        return result
```

### 在Tool中使用

```python
from app.sandbox.client import create_shared_sandbox_client

class PythonExecute(BaseTool):
    async def _execute_in_sandbox(self, code: str, timeout: int) -> Dict:
        # 使用共享sandbox，tag为"python_execute"
        sandbox_client = create_shared_sandbox_client(tag="python_execute")

        try:
            await sandbox_client.create()
            # 执行代码...
            output = await sandbox_client.run_command(f"python {script_path}", timeout)
        finally:
            await sandbox_client.cleanup()

        return {"observation": output, "success": True}
```

## 并发场景

多个agent进程可以同时使用相同tag的sandbox：

```python
# Agent进程1
client1 = create_shared_sandbox_client(tag="python_execute")
await client1.create()  # 创建sandbox A，ref_count=1

# Agent进程2（并发）
client2 = create_shared_sandbox_client(tag="python_execute")
await client2.create()  # 复用sandbox A，ref_count=2

# Agent进程1完成
await client1.cleanup()  # ref_count=1

# Agent进程2完成
await client2.cleanup()  # ref_count=0，空闲超时后自动清理
```

## 注意事项

1. **引用计数**: 每次`create()`会增加引用计数，每次`cleanup()`会减少引用计数
2. **自动清理**: 只有当引用计数为0且空闲超时后，sandbox才会被清理
3. **并发安全**: 使用异步锁确保并发安全
4. **资源限制**: 每个tag最多创建`max_sandboxes_per_tag`个sandbox
5. **隔离性**: 不同tag的sandbox是隔离的，不会共享

## 监控和统计

```python
from app.sandbox.core.shared_pool import get_shared_pool

pool = get_shared_pool()
stats = pool.get_stats()

print(stats)
# {
#     "total_sandboxes": 3,
#     "pools_by_tag": {"python_execute": 2, "file_ops": 1},
#     "ref_counts": {"sandbox_id_1": 2, "sandbox_id_2": 0, ...},
#     "active_operations": 1,
#     "max_sandboxes_per_tag": 5,
#     "idle_timeout": 3600,
# }
```

## 迁移指南

### 从LocalSandboxClient迁移到SharedSandboxClient

**之前**:
```python
from app.sandbox.client import SANDBOX_CLIENT

await SANDBOX_CLIENT.create()
await SANDBOX_CLIENT.run_command("...")
await SANDBOX_CLIENT.cleanup()
```

**之后**:
```python
from app.sandbox.client import create_shared_sandbox_client

client = create_shared_sandbox_client(tag="your_tag")
await client.create()
await client.run_command("...")
await client.cleanup()
```

## 最佳实践

1. **合理使用tag**: 根据功能类型选择合适的tag，避免所有任务使用同一个tag
2. **及时释放**: 任务完成后及时调用`cleanup()`释放引用
3. **错误处理**: 使用try-finally确保即使出错也能释放引用
4. **监控资源**: 定期检查pool统计信息，调整配置参数

