import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional, Set
from collections import defaultdict
import fcntl

from app.config import SandboxSettings
from app.sandbox.core.sandbox import DockerSandbox
from app.logger import logger


class SharedSandboxPool:
    """共享Sandbox池管理器。

    支持按功能类型（tag）管理共享的sandbox实例，多个agent进程可以共享相同功能的sandbox。
    使用引用计数来跟踪每个sandbox的使用者数量，当引用计数为0且空闲超时后才清理。

    Attributes:
        max_sandboxes_per_tag: 每个tag类型允许的最大sandbox数量
        idle_timeout: Sandbox空闲超时时间（秒）
        cleanup_interval: 清理检查间隔（秒）
        _pools: 按tag分组的sandbox池 {tag: {sandbox_id: sandbox}}
        _ref_counts: Sandbox引用计数 {sandbox_id: count}
        _last_used: Sandbox最后使用时间 {sandbox_id: timestamp}
        _sandbox_tags: Sandbox所属tag {sandbox_id: tag}
        _locks: 每个tag的锁，用于并发控制
        _global_lock: 全局锁
    """

    _instance = None
    _lock = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SharedSandboxPool, cls).__new__(cls)
            cls._lock = asyncio.Lock()
        return cls._instance

    def __init__(
        self,
        max_sandboxes_per_tag: int = 5,
        max_concurrency_per_sandbox: Optional[int] = 100,
        idle_timeout: int = 3600,
        cleanup_interval: int = 300,
    ):
        """初始化共享Sandbox池。

        Args:
            max_sandboxes_per_tag: 每个tag类型允许的最大sandbox数量
            max_concurrency_per_sandbox: 每个sandbox允许同时被引用的最大次数（None表示无限制）
            idle_timeout: Sandbox空闲超时时间（秒）
            cleanup_interval: 清理检查间隔（秒）
        """
        if hasattr(self, '_initialized'):
            return

        self.max_sandboxes_per_tag = max_sandboxes_per_tag
        self.max_concurrency_per_sandbox = max_concurrency_per_sandbox
        self.idle_timeout = idle_timeout
        self.cleanup_interval = cleanup_interval

        # 按tag分组的sandbox池
        self._pools: Dict[str, Dict[str, DockerSandbox]] = defaultdict(dict)

        # 引用计数和元数据
        self._ref_counts: Dict[str, int] = {}
        self._last_used: Dict[str, float] = {}
        self._sandbox_tags: Dict[str, str] = {}
        self._active_operations: Set[str] = set()

        # 并发控制
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

        # 清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._is_shutting_down = False

        # 跨进程共享：使用文件系统存储sandbox注册信息
        self._registry_dir = Path(tempfile.gettempdir()) / "openmanus_sandbox_registry"
        self._registry_dir.mkdir(parents=True, exist_ok=True)
        self._registry_lock_file = self._registry_dir / ".lock"
        self._manager_pid_file = self._registry_dir / "manager.pid"

        self._initialized = True

    def is_manager_running(self) -> bool:
        """检查Pool Manager服务是否正在运行。"""
        if not self._manager_pid_file.exists():
            return False

        try:
            with open(self._manager_pid_file, 'r') as f:
                pid = int(f.read().strip())

            # 检查进程是否存在
            os.kill(pid, 0)  # 发送信号0，不实际发送，只检查进程是否存在
            return True
        except (OSError, ValueError):
            # 进程不存在或PID文件无效
            self._manager_pid_file.unlink(missing_ok=True)
            return False

    def start_cleanup_task(self) -> None:
        """启动自动清理任务。

        如果Pool Manager正在运行，则不启动本地清理任务（由Manager负责）。
        """
        # 检查Manager是否运行
        if self.is_manager_running():
            logger.debug("Pool Manager is running, skipping local cleanup task")
            return

        # 只能在有运行中的事件循环里调用
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行中的事件循环时，先跳过，等到第一次在异步环境中使用池时再启动
            return

        async def cleanup_loop():
            while not self._is_shutting_down:
                # 再次检查Manager是否启动（可能在运行过程中启动了Manager）
                if self.is_manager_running():
                    logger.info("Pool Manager started, stopping local cleanup task")
                    break

                try:
                    await self._cleanup_idle_sandboxes()
                except Exception as e:
                    logger.error(f"Error in shared sandbox cleanup loop: {e}")
                await asyncio.sleep(self.cleanup_interval)

        self._cleanup_task = asyncio.create_task(cleanup_loop())

    async def acquire_sandbox(
        self,
        tag: str = "default",
        config: Optional[SandboxSettings] = None,
        volume_bindings: Optional[Dict[str, str]] = None,
    ) -> str:
        """获取或创建一个共享sandbox。

        Args:
            tag: Sandbox功能类型标签（如"python_execute", "file_ops"等）
            config: Sandbox配置
            volume_bindings: Volume映射配置

        Returns:
            str: Sandbox ID

        Raises:
            RuntimeError: 如果创建失败或达到最大数量限制
        """
        # 确保全局锁存在
        if self._lock is None:
            self._lock = asyncio.Lock()

        async with self._lock:
            # 获取或创建tag对应的锁
            if tag not in self._locks:
                self._locks[tag] = asyncio.Lock()

            # Agent进程不启动清理任务，清理工作完全由Manager负责
            # 如果Manager没有运行，也不会启动本地清理任务（避免进程无法退出）

        async with self._locks[tag]:
            pool = self._pools[tag]

            # 1. 先尝试从本地池中获取
            selected_sandbox_id = await self._select_available_sandbox(tag, pool)
            if selected_sandbox_id:
                # 更新注册表中的 last_used 时间（已在_select_available_sandbox中更新ref_count）
                asyncio.create_task(self._update_registry_last_used(selected_sandbox_id, tag))

                # 获取跨进程引用计数用于日志
                registry_info = await self._read_registry_with_ref_count(selected_sandbox_id, tag)
                cross_process_ref = registry_info.get("ref_count", 0) if registry_info else 0

                logger.info(
                    f"Reusing local sandbox {selected_sandbox_id} for tag '{tag}', "
                    f"local_ref_count={self._ref_counts[selected_sandbox_id]}, "
                    f"cross_process_ref_count={cross_process_ref}"
                )
                return selected_sandbox_id

            # 2. 尝试从跨进程注册表中查找可用的sandbox
            cross_process_sandbox_id = await self._find_cross_process_sandbox(tag)
            if cross_process_sandbox_id:
                # 验证并加载到本地池
                if await self._load_sandbox_from_registry(cross_process_sandbox_id, tag, config, volume_bindings):
                    selected_sandbox_id = await self._select_available_sandbox(tag, pool)
                    if selected_sandbox_id:
                        # 更新注册表中的 last_used 时间（已在_select_available_sandbox中更新ref_count）
                        asyncio.create_task(self._update_registry_last_used(selected_sandbox_id, tag))

                        # 获取跨进程引用计数用于日志
                        registry_info = await self._read_registry_with_ref_count(selected_sandbox_id, tag)
                        cross_process_ref = registry_info.get("ref_count", 0) if registry_info else 0

                        logger.info(
                            f"Reusing cross-process sandbox {selected_sandbox_id} for tag '{tag}', "
                            f"local_ref_count={self._ref_counts[selected_sandbox_id]}, "
                            f"cross_process_ref_count={cross_process_ref}"
                        )
                        return selected_sandbox_id

            # 3. 检查是否达到最大数量（包括注册表中的）
            total_count = await self._count_sandboxes_for_tag(tag)
            if total_count >= self.max_sandboxes_per_tag:
                raise RuntimeError(
                    f"Maximum number of sandboxes ({self.max_sandboxes_per_tag}) "
                    f"reached for tag '{tag}'"
                )

            # 4. 创建新的sandbox并注册
            try:
                config = config or SandboxSettings()
                sandbox = DockerSandbox(config, volume_bindings)
                await sandbox.create()

                # 使用container的ID作为sandbox_id
                if sandbox.container:
                    sandbox_id = sandbox.container.id
                else:
                    import uuid
                    sandbox_id = f"sandbox_{uuid.uuid4().hex[:8]}"

                pool[sandbox_id] = sandbox
                self._ref_counts[sandbox_id] = 1
                self._last_used[sandbox_id] = time.time()
                self._sandbox_tags[sandbox_id] = tag

                # 注册到跨进程注册表
                await self._register_sandbox(sandbox_id, tag, sandbox.container.id if sandbox.container else sandbox_id)
                # 新创建的sandbox，注册时已经包含了最新的last_used时间，无需再次更新

                logger.info(f"Created new shared sandbox {sandbox_id} for tag '{tag}'")
                return sandbox_id

            except Exception as e:
                logger.error(f"Failed to create shared sandbox for tag '{tag}': {e}")
                raise RuntimeError(f"Failed to create shared sandbox: {e}")

    async def release_sandbox(self, sandbox_id: str) -> None:
        """释放sandbox的引用。

        Agent进程只负责释放引用和更新注册表，不执行实际的清理操作。
        清理工作完全由Manager负责。

        Args:
            sandbox_id: Sandbox ID
        """
        if sandbox_id not in self._ref_counts:
            logger.warning(f"Attempted to release unknown sandbox {sandbox_id}")
            return

        async with self._global_lock:
            if sandbox_id in self._ref_counts:
                self._ref_counts[sandbox_id] = max(0, self._ref_counts[sandbox_id] - 1)
                self._last_used[sandbox_id] = time.time()

                # 更新注册表中的ref_count和last_used时间（非阻塞，避免多进程竞争）
                tag = self._sandbox_tags.get(sandbox_id)
                if tag:
                    # 异步更新跨进程引用计数（使用乐观锁）
                    asyncio.create_task(self._update_registry_ref_count(sandbox_id, tag, -1))
                    # 异步更新last_used时间
                    asyncio.create_task(self._update_registry_last_used(sandbox_id, tag))

                logger.info(
                    f"Released sandbox {sandbox_id}, "
                    f"local_ref_count={self._ref_counts[sandbox_id]}"
                )

                # Agent进程退出时，关闭本地创建的Docker client（但不清理container）
                # 这样可以释放连接，让进程正常退出
                if self._ref_counts[sandbox_id] == 0:
                    # 从本地池中移除，但保留在注册表中（由Manager清理）
                    if tag and sandbox_id in self._pools.get(tag, {}):
                        sandbox = self._pools[tag][sandbox_id]
                        # 关闭Docker client以释放连接
                        if sandbox and sandbox.client:
                            try:
                                sandbox.client.close()
                            except Exception as e:
                                logger.debug(f"Error closing client for sandbox {sandbox_id}: {e}")
                        # 从本地池中移除（但不清理container）
                        del self._pools[tag][sandbox_id]
                        # 清理引用计数和元数据
                        self._ref_counts.pop(sandbox_id, None)
                        self._last_used.pop(sandbox_id, None)
                        self._sandbox_tags.pop(sandbox_id, None)

    async def get_sandbox(self, sandbox_id: str) -> Optional[DockerSandbox]:
        """获取sandbox实例。

        Args:
            sandbox_id: Sandbox ID

        Returns:
            DockerSandbox实例，如果不存在则返回None
        """
        async with self._global_lock:
            for pool in self._pools.values():
                if sandbox_id in pool:
                    return pool[sandbox_id]
        return None

    async def _select_available_sandbox(self, tag: str, pool: Dict[str, DockerSandbox]) -> Optional[str]:
        """选择一个可用的sandbox（支持多引用）。

        优先选择引用计数最小且仍然运行的sandbox。
        会检查跨进程引用计数（从注册表读取）。
        """
        invalid_sandboxes = []
        candidates = []

        for sandbox_id, sandbox in pool.items():
            is_running = self._is_sandbox_running(sandbox)
            if not is_running:
                invalid_sandboxes.append(sandbox_id)
                continue

            # 获取本地引用计数
            local_ref = self._ref_counts.get(sandbox_id, 0)

            # 获取跨进程引用计数（从注册表读取）
            registry_info = await self._read_registry_with_ref_count(sandbox_id, tag)
            cross_process_ref = registry_info.get("ref_count", 0) if registry_info else 0

            # 使用跨进程引用计数检查限制（更准确）
            total_ref = max(local_ref, cross_process_ref)

            if (
                self.max_concurrency_per_sandbox is not None
                and total_ref >= self.max_concurrency_per_sandbox
            ):
                logger.debug(
                    f"Sandbox {sandbox_id[:12]}... exceeds max_concurrency "
                    f"(local_ref={local_ref}, cross_process_ref={cross_process_ref}, limit={self.max_concurrency_per_sandbox})"
                )
                continue

            # 使用本地引用计数作为排序依据（优先选择本地引用少的）
            candidates.append((local_ref, sandbox_id))

        for sandbox_id in invalid_sandboxes:
            await self._remove_sandbox(sandbox_id, tag)

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        selected_id = candidates[0][1]

        # 更新本地引用计数
        self._ref_counts[selected_id] = self._ref_counts.get(selected_id, 0) + 1
        self._last_used[selected_id] = time.time()

        # 异步更新跨进程引用计数（使用乐观锁）
        asyncio.create_task(self._update_registry_ref_count(selected_id, tag, +1))

        return selected_id

    def _is_sandbox_running(self, sandbox: DockerSandbox) -> bool:
        """检查sandbox容器是否仍在运行。"""
        try:
            if sandbox.container:
                sandbox.container.reload()
                return sandbox.container.status == "running"
        except Exception as exc:
            logger.warning(f"Sandbox {getattr(sandbox.container, 'id', 'unknown')} reload failed: {exc}")
        return False

    async def _find_cross_process_sandbox(self, tag: str) -> Optional[str]:
        """从跨进程注册表中查找可用的sandbox。"""
        try:
            # 扫描注册目录，查找匹配tag的sandbox
            for registry_file in self._registry_dir.glob(f"{tag}_*.json"):
                try:
                    with open(registry_file, 'r') as f:
                        registry_data = json.load(f)

                    sandbox_id = registry_data.get("sandbox_id")
                    container_id = registry_data.get("container_id")
                    last_used = registry_data.get("last_used", 0)

                    # 检查是否过期
                    if time.time() - last_used > self.idle_timeout:
                        continue

                    # 验证Docker容器是否真的存在且运行
                    if await self._verify_container_exists(container_id):
                        return sandbox_id
                except Exception as e:
                    logger.debug(f"Failed to read registry file {registry_file}: {e}")
                    continue
        except Exception as e:
            logger.debug(f"Error scanning cross-process registry: {e}")

        return None

    async def _verify_container_exists(self, container_id: str) -> bool:
        """验证Docker容器是否存在且运行。"""
        client = None
        try:
            import docker
            client = docker.from_env()
            container = client.containers.get(container_id)
            container.reload()
            return container.status == "running"
        except Exception:
            return False
        finally:
            # 关闭临时client以释放连接
            if client:
                try:
                    client.close()
                except Exception:
                    pass

    async def _load_sandbox_from_registry(self, sandbox_id: str, tag: str, config: Optional[SandboxSettings], volume_bindings: Optional[Dict[str, str]]) -> bool:
        """从注册表加载sandbox到本地池。"""
        try:
            registry_file = self._registry_dir / f"{tag}_{sandbox_id}.json"
            if not registry_file.exists():
                return False

            with open(registry_file, 'r') as f:
                registry_data = json.load(f)

            container_id = registry_data.get("container_id")
            if not container_id:
                return False

            # 验证容器存在
            if not await self._verify_container_exists(container_id):
                # 容器不存在，删除注册文件
                registry_file.unlink(missing_ok=True)
                return False

            # 创建DockerSandbox实例（不重新创建容器，只是连接到现有容器）
            import docker
            client = docker.from_env()
            container = client.containers.get(container_id)

            # 创建sandbox实例并连接到现有容器
            config = config or SandboxSettings()
            sandbox = DockerSandbox(config, volume_bindings)
            sandbox.container = container
            sandbox.client = client

            # 添加到本地池
            pool = self._pools[tag]
            # 如果sandbox已经在本地池中，不要覆盖已有的引用计数
            if sandbox_id not in pool:
                pool[sandbox_id] = sandbox
                # 从注册表读取跨进程引用计数，但本地引用计数从0开始
                registry_info = await self._read_registry_with_ref_count(sandbox_id, tag)
                self._ref_counts[sandbox_id] = 0  # 本地引用计数初始为0，会在_select_available_sandbox中增加
                self._last_used[sandbox_id] = time.time()
                self._sandbox_tags[sandbox_id] = tag
                logger.info(
                    f"Loaded sandbox {sandbox_id} from cross-process registry for tag '{tag}' "
                    f"(cross_process_ref_count={registry_info.get('ref_count', 0) if registry_info else 0})"
                )
            else:
                # 如果已经在本地池中，只更新sandbox实例（可能容器状态有变化）
                pool[sandbox_id] = sandbox
                # 保持已有的本地引用计数，不重置为0
                logger.info(f"Sandbox {sandbox_id} already in local pool for tag '{tag}', updated instance only")
            return True
        except Exception as e:
            logger.warning(f"Failed to load sandbox from registry: {e}")
            return False

    async def _count_sandboxes_for_tag(self, tag: str) -> int:
        """统计某个tag的sandbox总数（包括本地和注册表中的）。

        使用union方式统计，避免重复计算。
        """
        # 获取本地sandbox ID集合
        local_sandbox_ids = set(self._pools[tag].keys())

        # 获取注册表中的sandbox ID集合
        registry_sandbox_ids = set()
        try:
            for registry_file in self._registry_dir.glob(f"{tag}_*.json"):
                try:
                    with open(registry_file, 'r') as f:
                        registry_data = json.load(f)
                    sandbox_id = registry_data.get("sandbox_id")
                    container_id = registry_data.get("container_id")
                    if sandbox_id and container_id and await self._verify_container_exists(container_id):
                        registry_sandbox_ids.add(sandbox_id)
                except Exception:
                    continue
        except Exception:
            pass

        # 使用union统计唯一sandbox数量（避免重复计算）
        total_unique_sandboxes = len(local_sandbox_ids | registry_sandbox_ids)
        return total_unique_sandboxes

    async def _register_sandbox(self, sandbox_id: str, tag: str, container_id: str) -> None:
        """注册sandbox到跨进程注册表。"""
        try:
            registry_file = self._registry_dir / f"{tag}_{sandbox_id}.json"
            registry_data = {
                "sandbox_id": sandbox_id,
                "tag": tag,
                "container_id": container_id,
                "created_at": time.time(),
                "last_used": time.time(),
                "ref_count": 1,  # 初始引用计数为1（创建时）
                "version": 1,   # 版本号（乐观锁）
            }

            with open(registry_file, 'w') as f:
                json.dump(registry_data, f)

            logger.debug(f"Registered sandbox {sandbox_id} to cross-process registry")
        except Exception as e:
            logger.warning(f"Failed to register sandbox to registry: {e}")

    async def _unregister_sandbox(self, sandbox_id: str, tag: str) -> None:
        """从跨进程注册表中移除sandbox。"""
        try:
            registry_file = self._registry_dir / f"{tag}_{sandbox_id}.json"
            if registry_file.exists():
                registry_file.unlink()
                logger.debug(f"Unregistered sandbox {sandbox_id} from cross-process registry")
        except Exception as e:
            logger.warning(f"Failed to unregister sandbox from registry: {e}")

    async def _read_registry_with_ref_count(self, sandbox_id: str, tag: str) -> Optional[Dict]:
        """读取注册表，获取ref_count和version（用于乐观锁）。

        Returns:
            Dict包含ref_count和version，如果文件不存在则返回None
        """
        try:
            registry_file = self._registry_dir / f"{tag}_{sandbox_id}.json"
            if not registry_file.exists():
                return None

            with open(registry_file, 'r') as f:
                registry_data = json.load(f)

            return {
                "ref_count": registry_data.get("ref_count", 0),
                "version": registry_data.get("version", 0),
                "last_used": registry_data.get("last_used", 0),
            }
        except Exception as e:
            logger.debug(f"Failed to read registry for sandbox {sandbox_id[:12]}...: {e}")
            return None

    async def _update_registry_ref_count(
        self,
        sandbox_id: str,
        tag: str,
        delta: int,
        max_retries: int = 3
    ) -> bool:
        """使用乐观锁更新注册表中的ref_count。

        Args:
            sandbox_id: Sandbox ID
            tag: Tag
            delta: 引用计数的变化量（+1表示acquire，-1表示release）
            max_retries: 最大重试次数（乐观锁冲突时）

        Returns:
            bool: 是否更新成功
        """
        registry_file = self._registry_dir / f"{tag}_{sandbox_id}.json"
        if not registry_file.exists():
            logger.warning(f"Registry file not found for sandbox {sandbox_id[:12]}...")
            return False

        for attempt in range(max_retries):
            try:
                # 读取当前值
                with open(registry_file, 'r') as f:
                    registry_data = json.load(f)

                old_version = registry_data.get("version", 0)
                old_ref_count = registry_data.get("ref_count", 0)

                # 计算新值
                new_ref_count = max(0, old_ref_count + delta)
                new_version = old_version + 1

                # 写入新值（使用文件锁保护，避免并发写入）
                lock_file = registry_file.with_suffix('.lock')
                try:
                    with open(lock_file, 'w') as lock:
                        try:
                            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                            # 再次读取，验证版本号（乐观锁检查）
                            with open(registry_file, 'r') as f:
                                current_data = json.load(f)

                            if current_data.get("version", 0) != old_version:
                                # 版本号已变化，说明有其他进程修改了，需要重试
                                logger.debug(
                                    f"Version conflict for sandbox {sandbox_id[:12]}... "
                                    f"(expected {old_version}, got {current_data.get('version', 0)}), retrying..."
                                )
                                continue

                            # 版本号匹配，更新数据
                            registry_data["ref_count"] = new_ref_count
                            registry_data["version"] = new_version
                            registry_data["last_used"] = time.time()

                            with open(registry_file, 'w') as f:
                                json.dump(registry_data, f)

                            logger.debug(
                                f"Updated registry ref_count for sandbox {sandbox_id[:12]}... "
                                f"(ref_count: {old_ref_count} -> {new_ref_count}, version: {old_version} -> {new_version})"
                            )
                            return True

                        except BlockingIOError:
                            # 锁被占用，等待一小段时间后重试
                            await asyncio.sleep(0.01 * (attempt + 1))  # 递增等待时间
                            continue
                        finally:
                            try:
                                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                            except Exception:
                                pass
                            lock_file.unlink(missing_ok=True)

                except Exception as e:
                    logger.debug(f"Error updating registry ref_count for sandbox {sandbox_id[:12]}...: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.01 * (attempt + 1))
                        continue
                    return False

            except Exception as e:
                logger.debug(f"Failed to update registry ref_count for sandbox {sandbox_id[:12]}...: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.01 * (attempt + 1))
                    continue
                return False

        logger.warning(f"Failed to update registry ref_count for sandbox {sandbox_id[:12]}... after {max_retries} retries")
        return False

    async def _update_registry_last_used(self, sandbox_id: str, tag: str) -> None:
        """更新注册表中的last_used时间（非阻塞）。"""
        try:
            registry_file = self._registry_dir / f"{tag}_{sandbox_id}.json"
            if not registry_file.exists():
                return

            # 使用文件锁避免多进程竞争
            lock_file = registry_file.with_suffix('.lock')
            try:
                # 非阻塞锁，如果锁被占用就跳过更新（避免阻塞）
                with open(lock_file, 'w') as lock:
                    try:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        # 读取-修改-写入
                        with open(registry_file, 'r') as f:
                            registry_data = json.load(f)
                        registry_data["last_used"] = time.time()
                        with open(registry_file, 'w') as f:
                            json.dump(registry_data, f)
                        logger.debug(f"Updated registry last_used for sandbox {sandbox_id[:12]}...")
                    except BlockingIOError:
                        # 锁被占用，跳过更新（避免阻塞）
                        logger.debug(f"Registry file locked for sandbox {sandbox_id[:12]}..., skipping update")
                    finally:
                        try:
                            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                        except Exception:
                            pass
                        lock_file.unlink(missing_ok=True)
            except Exception as e:
                # 如果锁操作失败，记录日志但不阻塞
                logger.debug(f"Error updating registry last_used for sandbox {sandbox_id[:12]}...: {e}")
        except Exception as e:
            logger.debug(f"Failed to update registry last_used: {e}")

    async def _remove_sandbox(self, sandbox_id: str, tag: Optional[str] = None) -> None:
        """移除sandbox（内部方法）。

        Args:
            sandbox_id: Sandbox ID
            tag: Sandbox所属tag，如果为None则自动查找
        """
        if tag is None:
            tag = self._sandbox_tags.get(sandbox_id)
            if tag is None:
                # 在所有池中查找
                for t, pool in self._pools.items():
                    if sandbox_id in pool:
                        tag = t
                        break

        if tag and sandbox_id in self._pools.get(tag, {}):
            sandbox = self._pools[tag][sandbox_id]
            try:
                await sandbox.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up sandbox {sandbox_id}: {e}")

            del self._pools[tag][sandbox_id]
            self._ref_counts.pop(sandbox_id, None)
            self._last_used.pop(sandbox_id, None)
            self._sandbox_tags.pop(sandbox_id, None)
            self._active_operations.discard(sandbox_id)

            # 从跨进程注册表中移除
            await self._unregister_sandbox(sandbox_id, tag)

            logger.info(f"Removed sandbox {sandbox_id} from tag '{tag}'")

    async def _cleanup_idle_sandboxes(self) -> None:
        """清理空闲的sandbox。

        如果Pool Manager正在运行，只清理本地池中的sandbox。
        跨进程的sandbox由Manager负责清理。
        """
        current_time = time.time()
        to_cleanup = []

        # 只清理本地池中的sandbox
        async with self._global_lock:
            for sandbox_id, ref_count in list(self._ref_counts.items()):
                if (
                    ref_count == 0
                    and sandbox_id not in self._active_operations
                    and current_time - self._last_used.get(sandbox_id, 0) > self.idle_timeout
                ):
                    to_cleanup.append(sandbox_id)

        for sandbox_id in to_cleanup:
            try:
                await self._remove_sandbox(sandbox_id)
            except Exception as e:
                logger.error(f"Error cleaning up idle sandbox {sandbox_id}: {e}")

        # 如果Manager没有运行，也清理跨进程注册表中的过期sandbox（降级模式）
        if not self.is_manager_running():
            await self._cleanup_cross_process_sandboxes()

    async def _cleanup_cross_process_sandboxes(self) -> None:
        """清理跨进程注册表中的过期sandbox（降级模式，当Manager未运行时使用）。"""
        current_time = time.time()

        try:
            for registry_file in self._registry_dir.glob("*.json"):
                # 跳过PID文件
                if registry_file.name == "manager.pid":
                    continue

                try:
                    with open(registry_file, 'r') as f:
                        registry_data = json.load(f)

                    container_id = registry_data.get("container_id")
                    tag = registry_data.get("tag")
                    last_used = registry_data.get("last_used", 0)

                    if not container_id or not tag:
                        registry_file.unlink(missing_ok=True)
                        continue

                    # 检查是否过期
                    is_expired = current_time - last_used > self.idle_timeout

                    # 验证容器是否存在
                    container_exists = await self._verify_container_exists(container_id)

                    if not container_exists:
                        registry_file.unlink(missing_ok=True)
                    elif is_expired:
                        # 尝试清理过期容器
                        try:
                            import docker
                            client = docker.from_env()
                            container = client.containers.get(container_id)
                            container.stop(timeout=5)
                            container.remove(force=True)
                            registry_file.unlink(missing_ok=True)
                        except Exception as e:
                            logger.debug(f"Failed to cleanup expired container {container_id[:12]}...: {e}")

                except Exception as e:
                    logger.debug(f"Error processing registry file {registry_file.name}: {e}")

        except Exception as e:
            logger.debug(f"Error in cross-process cleanup: {e}")

    async def cleanup(self) -> None:
        """清理所有资源。"""
        logger.info("Starting shared sandbox pool cleanup...")
        self._is_shutting_down = True

        # 取消清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await asyncio.wait_for(self._cleanup_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # 清理所有sandbox
        async with self._global_lock:
            all_sandbox_ids = list(self._ref_counts.keys())

        cleanup_tasks = []
        for sandbox_id in all_sandbox_ids:
            task = asyncio.create_task(self._remove_sandbox(sandbox_id))
            cleanup_tasks.append(task)

        if cleanup_tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*cleanup_tasks, return_exceptions=True), timeout=30.0)
            except asyncio.TimeoutError:
                logger.error("Shared sandbox pool cleanup timed out")

        # 清理所有引用
        self._pools.clear()
        self._ref_counts.clear()
        self._last_used.clear()
        self._sandbox_tags.clear()
        self._locks.clear()
        self._active_operations.clear()

        logger.info("Shared sandbox pool cleanup completed")

    def get_stats(self) -> Dict:
        """获取池统计信息。

        Returns:
            Dict: 统计信息
        """
        return {
            "total_sandboxes": sum(len(pool) for pool in self._pools.values()),
            "pools_by_tag": {tag: len(pool) for tag, pool in self._pools.items()},
            "ref_counts": dict(self._ref_counts),
            "active_operations": len(self._active_operations),
            "max_sandboxes_per_tag": self.max_sandboxes_per_tag,
            "max_concurrency_per_sandbox": self.max_concurrency_per_sandbox,
            "idle_timeout": self.idle_timeout,
        }


# 全局单例实例
_shared_pool_instance: Optional[SharedSandboxPool] = None


def get_shared_pool() -> SharedSandboxPool:
    """获取共享sandbox池的单例实例。

    Returns:
        SharedSandboxPool: 单例实例
    """
    global _shared_pool_instance
    if _shared_pool_instance is None:
        _shared_pool_instance = SharedSandboxPool()
    return _shared_pool_instance

