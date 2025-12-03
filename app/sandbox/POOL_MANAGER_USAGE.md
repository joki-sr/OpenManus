# Pool Manager 使用指南

## 概述

Pool Manager 是一个独立的守护进程，负责管理跨进程的 sandbox 生命周期。它解决了多进程环境下 sandbox 共享和清理的问题。

## 架构

```
┌─────────────────┐
│  Pool Manager   │  ← 独立进程，手动启动
│   (守护进程)    │
│  - 扫描注册表   │
│  - 清理过期容器 │
└────────┬────────┘
         │
    (文件系统)
         │
    ┌────┴────┬────────┬────────┐
    │         │        │        │
┌───▼───┐ ┌──▼───┐ ┌──▼───┐ ┌──▼───┐
│Agent1 │ │Agent2│ │Agent3│ │Agent4│
│(客户端)│ │(客户端)│ │(客户端)│ │(客户端)│
└───────┘ └──────┘ └──────┘ └──────┘
```

## 使用方法

### 1. 启动 Pool Manager

```bash
# 方式1：使用启动脚本
python app/sandbox/start_pool_manager.py

# 方式2：直接运行模块
python -m app.sandbox.core.pool_manager

# 方式3：带参数运行
python -m app.sandbox.core.pool_manager \
    --idle-timeout 3600 \
    --cleanup-interval 300
```

### 2. 运行 Agent 进程

启动 Manager 后，Agent 进程会自动检测到 Manager 正在运行，并：
- 使用 Manager 管理的 sandbox
- 不启动自己的清理任务（由 Manager 负责）

```bash
# 正常运行 agent，无需特殊配置
python main.py --prompt "your task"
```

### 3. 停止 Pool Manager

```bash
# 方式1：发送 SIGTERM 信号
kill <PID>

# 方式2：发送 SIGINT 信号（Ctrl+C）
# 如果在终端运行，直接按 Ctrl+C
```

## 配置参数

### Pool Manager 参数

- `--idle-timeout`: Sandbox 空闲超时时间（秒），默认 3600（1小时）
- `--cleanup-interval`: 清理检查间隔（秒），默认 300（5分钟）
- `--registry-dir`: 注册表目录路径，默认使用系统临时目录
- `--pid-file`: PID 文件路径，默认 `registry_dir/manager.pid`

### 示例

```bash
# 更频繁的清理（每1分钟检查一次）
python -m app.sandbox.core.pool_manager --cleanup-interval 60

# 更短的超时时间（30分钟后清理）
python -m app.sandbox.core.pool_manager --idle-timeout 1800
```

## 工作原理

### 1. Manager 进程

- 定期扫描注册表目录（`/tmp/openmanus_sandbox_registry/`）
- 验证 Docker 容器是否存在
- 清理过期的容器和无效的注册文件
- 通过 PID 文件标识自己正在运行

### 2. Agent 进程

- 启动时检查 Manager 是否运行（通过 PID 文件）
- 如果 Manager 运行：不启动本地清理任务，只管理本地池
- 如果 Manager 未运行：启动本地清理任务（降级模式）

### 3. 跨进程共享

- Agent 创建 sandbox 时，注册到文件系统
- 其他 Agent 通过扫描注册表发现可用的 sandbox
- 通过 Docker API 验证容器存在性
- 使用文件系统作为轻量级的共享机制

## 优势

1. **集中管理**：所有清理逻辑集中在一个进程
2. **简单可靠**：基于文件系统，无需网络通信
3. **容错性强**：即使 Manager 挂了，Agent 仍可工作（降级模式）
4. **易于监控**：可以查看 PID 文件和日志

## 降级模式

如果 Pool Manager 未运行，Agent 进程会：
- 启动自己的清理任务
- 同时清理本地池和跨进程注册表
- 功能完全可用，只是清理逻辑分散在各个进程

## 故障排查

### 检查 Manager 是否运行

```bash
# 查看 PID 文件
cat /tmp/openmanus_sandbox_registry/manager.pid

# 检查进程
ps aux | grep pool_manager
```

### 查看注册表

```bash
# 列出所有注册的 sandbox
ls -la /tmp/openmanus_sandbox_registry/*.json
```

### 手动清理

如果 Manager 异常退出，可以手动清理：

```bash
# 删除所有注册文件（谨慎操作）
rm /tmp/openmanus_sandbox_registry/*.json

# 清理所有 sandbox 容器（通过 Docker）
docker ps -a | grep sandbox_ | awk '{print $1}' | xargs docker rm -f
```

## 注意事项

1. **确保 Manager 持续运行**：如果 Manager 停止，Agent 会切换到降级模式
2. **注册表目录**：默认使用系统临时目录，重启后可能丢失（但容器仍在）
3. **并发安全**：多个进程可以安全地同时访问注册表（通过 Docker API 的原子性）

