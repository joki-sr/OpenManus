# 共享Sandbox实现总结

## 实现概述

已成功实现支持多agent进程并发并共享特定功能sandbox的完整方案。

## 核心功能

### 1. SharedSandboxPool（共享池管理器）

**文件**: `app/sandbox/core/shared_pool.py`

**功能**:
- 按功能类型（tag）管理多个sandbox池
- 使用引用计数跟踪每个sandbox的使用者数量
- 自动清理空闲的sandbox（引用计数为0且空闲超时）
- 支持并发安全的sandbox获取和释放

**关键特性**:
- 单例模式，全局共享
- 每个tag最多可创建`max_sandboxes_per_tag`个sandbox
- 自动检测和清理无效的sandbox
- 支持自定义配置（内存、CPU、超时等）

### 2. SharedSandboxClient（共享客户端）

**文件**: `app/sandbox/client.py`

**功能**:
- 提供与`LocalSandboxClient`相同的接口
- 自动从共享池获取或创建sandbox
- 支持通过tag指定功能类型
- 自动管理引用计数

**使用方式**:
```python
from app.sandbox.client import create_shared_sandbox_client

client = create_shared_sandbox_client(tag="python_execute")
await client.create()  # 获取或创建共享sandbox
await client.run_command("...")
await client.cleanup()  # 释放引用
```

## 架构设计

### 工作流程

```
┌─────────────────┐
│  Agent进程1      │
│  tag="python"   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  SharedSandboxPool      │
│  ┌───────────────────┐  │
│  │ python_execute:   │  │
│  │ - sandbox_1 (ref=1)│ │
│  └───────────────────┘  │
│  ┌───────────────────┐  │
│  │ file_ops:         │  │
│  │ - sandbox_2 (ref=0)│ │
│  └───────────────────┘  │
└────────┬────────────────┘
         │
         ▼
┌─────────────────┐
│  Agent进程2      │
│  tag="python"   │
└─────────────────┘
   复用sandbox_1 (ref=2)
```

### 引用计数机制

1. **获取sandbox**: `acquire_sandbox()` → ref_count++
2. **释放sandbox**: `release_sandbox()` → ref_count--
3. **自动清理**: ref_count == 0 且空闲超时 → 清理sandbox

## 文件结构

```
app/sandbox/
├── __init__.py                    # 导出新类和函数
├── client.py                       # 添加SharedSandboxClient
├── core/
│   ├── shared_pool.py             # 共享池管理器（新增）
│   ├── sandbox.py                 # 原有DockerSandbox（未修改）
│   └── manager.py                 # 原有SandboxManager（未修改）
├── SHARED_SANDBOX_USAGE.md        # 使用指南（新增）
├── example_usage.py                # 使用示例（新增）
└── IMPLEMENTATION_SUMMARY.md       # 本文档（新增）
```

## 使用场景

### 场景1: 多个Agent共享Python执行Sandbox

```python
# Agent 1
client1 = create_shared_sandbox_client(tag="python_execute")
await client1.create()  # 创建sandbox A

# Agent 2（并发）
client2 = create_shared_sandbox_client(tag="python_execute")
await client2.create()  # 复用sandbox A

# Agent 1完成
await client1.cleanup()  # ref_count: 2 -> 1

# Agent 2完成
await client2.cleanup()  # ref_count: 1 -> 0，空闲超时后清理
```

### 场景2: 不同功能使用不同Sandbox

```python
# Python执行
python_client = create_shared_sandbox_client(tag="python_execute")
await python_client.create()

# 文件操作（不同的sandbox）
file_client = create_shared_sandbox_client(tag="file_ops")
await file_client.create()
```

## 配置参数

### SharedSandboxPool参数

- `max_sandboxes_per_tag`: 每个tag最多sandbox数量（默认5）
- `idle_timeout`: 空闲超时时间，秒（默认3600）
- `cleanup_interval`: 清理检查间隔，秒（默认300）

### 自定义配置示例

```python
from app.sandbox.core.shared_pool import SharedSandboxPool

# 自定义池配置
pool = SharedSandboxPool(
    max_sandboxes_per_tag=10,
    idle_timeout=7200,  # 2小时
    cleanup_interval=600,  # 10分钟
)
```

## 向后兼容性

- ✅ 保持`LocalSandboxClient`不变，现有代码无需修改
- ✅ 新增`SharedSandboxClient`，可选使用
- ✅ 两种client实现相同的接口，可以互换使用

## 优势

1. **减少容器创建开销**: 多个agent共享sandbox，避免频繁创建/销毁Docker容器，节省启动时间
2. **性能提升**: 复用已创建的sandbox，避免重复初始化（镜像拉取、容器启动等）
3. **支持高并发**: 通过docker exec在同一container内并发执行，支持100+ agent共享一个sandbox
4. **灵活配置**: 按功能类型隔离，不同任务使用不同sandbox
5. **自动管理**: 引用计数和自动清理，无需手动管理生命周期
6. **并发安全**: 使用异步锁确保多进程并发安全

**注意**: 内存占用主要来自agent进程本身（~512MB/进程），而非Docker container。共享pool的主要价值在于减少容器创建开销和提高并发执行效率，而非减少内存使用。

## 注意事项

1. **引用计数**: 必须成对调用`create()`和`cleanup()`
2. **错误处理**: 使用try-finally确保即使出错也能释放引用
3. **隔离性**: 不同tag的sandbox完全隔离，不会共享
4. **资源限制**: 每个tag有最大sandbox数量限制
5. **清理时机**: 只有当引用计数为0且空闲超时后才清理

## 迁移建议

### 对于新代码
直接使用`SharedSandboxClient`:
```python
from app.sandbox.client import create_shared_sandbox_client
client = create_shared_sandbox_client(tag="your_tag")
```

### 对于现有代码
可以逐步迁移，两种方式可以共存:
- 保持使用`LocalSandboxClient`（独立sandbox）
- 或迁移到`SharedSandboxClient`（共享sandbox）

## 测试建议

1. **并发测试**: 多个agent同时使用相同tag的sandbox
2. **引用计数测试**: 验证引用计数的正确性
3. **自动清理测试**: 验证空闲超时后的自动清理
4. **隔离测试**: 验证不同tag的sandbox隔离性
5. **错误恢复测试**: 验证无效sandbox的自动清理和重建

## 后续优化方向

1. **负载均衡**: 在多个可用sandbox中选择负载最低的
2. **健康检查**: 定期检查sandbox健康状态
3. **统计监控**: 更详细的统计信息和监控指标
4. **配置热更新**: 支持运行时更新配置参数
5. **持久化**: 支持sandbox状态的持久化存储

