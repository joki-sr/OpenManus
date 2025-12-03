# Sandbox获取流程详解

## 核心逻辑：先检查，后创建

当新的agent进程需要sandbox时，**总是先检查是否有空闲的sandbox**，只有找不到空闲的才会创建新的。

## 完整流程

```
1. Agent调用 create()
   ↓
2. 进入 acquire_sandbox()
   ↓
3. 【第一步】遍历池中所有sandbox，查找空闲的
   ├─ 检查引用计数是否为0
   ├─ 检查容器是否还在运行
   └─ 如果找到 → 复用并返回 ✓
   ↓
4. 【第二步】如果没找到空闲的
   ├─ 检查是否达到最大数量限制
   ├─ 如果达到 → 抛出异常
   └─ 如果没达到 → 创建新的sandbox
```

## 代码流程（shared_pool.py:91-174）

### 步骤1: 查找空闲sandbox（第121-141行）

```python
# 查找引用计数为0的可用sandbox
for sandbox_id, sandbox in pool.items():
    if self._ref_counts.get(sandbox_id, 0) == 0:  # ← 检查引用计数
        # 检查sandbox是否仍然有效
        if sandbox.container.status == 'running':
            # 找到空闲的！复用它
            self._ref_counts[sandbox_id] = 1
            return sandbox_id  # ← 直接返回，不创建新的
```

### 步骤2: 检查数量限制（第147-152行）

```python
# 如果没有可用的sandbox，检查是否达到最大数量
if len(pool) >= self.max_sandboxes_per_tag:
    raise RuntimeError("Maximum number of sandboxes reached")
```

### 步骤3: 创建新sandbox（第154-174行）

```python
# 只有在前两步都通过后，才创建新的sandbox
sandbox = DockerSandbox(config, volume_bindings)
await sandbox.create()
# ...
return sandbox_id
```

## 实际执行示例

### 场景1: 有空闲sandbox

```
Agent 1: create()
  ↓
检查池中sandbox
  ↓
找到 sandbox_A (ref_count=0, running)
  ↓
复用 sandbox_A ✓
  ↓
不创建新的
```

### 场景2: 没有空闲sandbox

```
Agent 2: create()
  ↓
检查池中sandbox
  ↓
sandbox_A (ref_count=1, 被占用)
sandbox_B (ref_count=1, 被占用)
  ↓
没有空闲的
  ↓
检查数量限制 (当前2个 < 最大5个)
  ↓
创建新的 sandbox_C ✓
```

## 从你的日志验证

```
时间 01.343s: Agent 0 创建sandbox_A → ref_count=1
时间 01.358s: Agent 1 create()
  ↓
  检查池中sandbox
  ↓
  sandbox_A: ref_count=1 (被占用)
  ↓
  没有空闲的
  ↓
  创建新的 sandbox_B ✓

时间 01.964s: Agent 0 cleanup() → sandbox_A ref_count=0 (空闲)
时间 02.069s: Agent 2 create()
  ↓
  检查池中sandbox
  ↓
  sandbox_A: ref_count=0 (空闲！) ✓
  sandbox_B: ref_count=1 (被占用)
  ↓
  找到空闲的sandbox_A
  ↓
  复用 sandbox_A ✓
  ↓
  不创建新的
```

## 关键点总结

| 步骤 | 操作 | 结果 |
|------|------|------|
| 1 | 检查池中是否有 ref_count=0 的sandbox | 有 → 复用 |
| 2 | 如果没有，检查是否达到最大数量 | 达到 → 异常 |
| 3 | 如果没达到，创建新的sandbox | 创建新sandbox |

## 设计优势

1. **资源复用**：优先复用空闲sandbox，减少资源消耗
2. **避免浪费**：不会无限制创建新sandbox
3. **并发安全**：使用锁确保并发时不会重复创建

## 总结

**是的，新进程创建sandbox之前会先检查有没有空闲的。**

- ✅ 先遍历池中所有sandbox
- ✅ 查找引用计数为0的空闲sandbox
- ✅ 如果找到，复用它
- ✅ 如果找不到，才创建新的

这就是为什么Agent 2能够复用Agent 0释放的sandbox的原因！

