# Sandbox "被占用" 的含义解释

## 重要概念澄清

### ❌ 误解："被占用" = 容器里有进程在运行

### ✅ 正确理解："被占用" = 引用计数 > 0

## 详细说明

### 1. 引用计数机制

"被占用"是一个**逻辑概念**，不是物理概念：

```python
# 在 shared_pool.py 中
if self._ref_counts.get(sandbox_id, 0) == 0:
    # 引用计数为0 = 可用（没有被占用）
    # 可以复用这个sandbox
else:
    # 引用计数 > 0 = 被占用
    # 需要创建新的sandbox
```

### 2. 引用计数的变化

```
Agent获取sandbox时：
  ref_count: 0 → 1  (被占用)

Agent释放sandbox时：
  ref_count: 1 → 0  (变为空闲)
```

### 3. 实际运行情况

**重要**：一个Docker容器**理论上可以同时执行多个命令**，但我们的设计是：

- 当一个agent调用 `create()` 时，引用计数 +1
- 其他agent看到引用计数 > 0，就认为"被占用"，会创建新的sandbox
- 当agent调用 `cleanup()` 时，引用计数 -1

### 4. 为什么这样设计？

**原因**：避免多个agent同时使用同一个sandbox导致：
- 文件冲突（写入相同路径）
- 状态混乱（一个agent的操作影响另一个）
- 难以追踪问题

## 实际示例

### 场景1：Agent 0 正在使用sandbox

```
时间点1:
  Agent 0: create() → ref_count = 1 (被占用)
  Agent 1: 尝试获取 → 发现 ref_count = 1 → 创建新sandbox
```

**此时**：
- Sandbox容器本身可能**没有**正在执行的命令
- Agent 0 可能已经执行完命令，但**还没有调用 cleanup()**
- 引用计数仍然 > 0，所以被认为是"被占用"

### 场景2：Agent 0 释放sandbox

```
时间点2:
  Agent 0: cleanup() → ref_count = 0 (空闲)
  Agent 2: 尝试获取 → 发现 ref_count = 0 → 复用这个sandbox
```

**此时**：
- Sandbox容器可能**仍然在运行**（Docker容器状态是running）
- 但引用计数 = 0，所以被认为是"可用"
- Agent 2 可以安全地使用这个sandbox

## 代码逻辑

```python
# shared_pool.py:124
for sandbox_id, sandbox in pool.items():
    if self._ref_counts.get(sandbox_id, 0) == 0:  # ← 关键判断
        # 引用计数为0 = 可用
        # 检查容器是否还在运行
        if sandbox.container.status == 'running':
            # 复用这个sandbox
            self._ref_counts[sandbox_id] = 1
            return sandbox_id
    # else: 引用计数 > 0 = 被占用，跳过这个sandbox
```

## 总结

| 概念 | 含义 |
|------|------|
| **被占用** | 引用计数 > 0，有agent正在"使用"这个sandbox |
| **空闲** | 引用计数 = 0，没有agent在使用 |
| **容器状态** | Docker容器的运行状态（running/stopped），与引用计数无关 |
| **进程状态** | 容器内是否有命令在执行，与引用计数无关 |

## 关键点

1. **引用计数是逻辑概念**，不是物理状态
2. **容器可以运行，但引用计数为0时仍然可用**
3. **设计目的是避免多个agent同时使用同一个sandbox**
4. **引用计数在 `create()` 时+1，在 `cleanup()` 时-1**

## 实际运行示例

从你的日志来看：

```
Agent 0: create() → ref_count = 1 (被占用)
Agent 1: 尝试获取 → ref_count = 1 → 创建新sandbox
Agent 0: cleanup() → ref_count = 0 (空闲)
Agent 2: 尝试获取 → ref_count = 0 → 复用sandbox ✓
```

**注意**：即使Agent 0已经执行完命令，只要它**还没有调用 cleanup()**，引用计数就仍然是1，sandbox就仍然"被占用"。


