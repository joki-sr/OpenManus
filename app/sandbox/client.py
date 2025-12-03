from abc import ABC, abstractmethod
from typing import Dict, Optional, Protocol

from app.config import SandboxSettings
from app.sandbox.core.sandbox import DockerSandbox
from app.sandbox.core.shared_pool import get_shared_pool
from app.logger import logger


class SandboxFileOperations(Protocol):
    """Protocol for sandbox file operations."""

    async def copy_from(self, container_path: str, local_path: str) -> None:
        """Copies file from container to local.

        Args:
            container_path: File path in container.
            local_path: Local destination path.
        """
        ...

    async def copy_to(self, local_path: str, container_path: str) -> None:
        """Copies file from local to container.

        Args:
            local_path: Local source file path.
            container_path: Destination path in container.
        """
        ...

    async def read_file(self, path: str) -> str:
        """Reads file content from container.

        Args:
            path: File path in container.

        Returns:
            str: File content.
        """
        ...

    async def write_file(self, path: str, content: str) -> None:
        """Writes content to file in container.

        Args:
            path: File path in container.
            content: Content to write.
        """
        ...


class BaseSandboxClient(ABC):
    """Base sandbox client interface."""

    @abstractmethod
    async def create(
        self,
        config: Optional[SandboxSettings] = None,
        volume_bindings: Optional[Dict[str, str]] = None,
    ) -> None:
        """Creates sandbox."""

    @abstractmethod
    async def run_command(self, command: str, timeout: Optional[int] = None) -> str:
        """Executes command."""

    @abstractmethod
    async def copy_from(self, container_path: str, local_path: str) -> None:
        """Copies file from container."""

    @abstractmethod
    async def copy_to(self, local_path: str, container_path: str) -> None:
        """Copies file to container."""

    @abstractmethod
    async def read_file(self, path: str) -> str:
        """Reads file."""

    @abstractmethod
    async def write_file(self, path: str, content: str) -> None:
        """Writes file."""

    @abstractmethod
    async def cleanup(self) -> None:
        """Cleans up resources."""


class LocalSandboxClient(BaseSandboxClient):
    _instance = None
    _lock = None  # 我们会在 __new__ 中初始化这个锁

    def __new__(cls):
        if cls._instance is None:
            import asyncio
            cls._instance = super(LocalSandboxClient, cls).__new__(cls)
            cls._lock = asyncio.Lock()  # 创建一个异步锁以确保线程安全
        return cls._instance

    def __init__(self):
        """Initializes local sandbox client."""
        # 只在第一次初始化时设置 sandbox
        if not hasattr(self, 'sandbox'):
            self.sandbox: Optional[DockerSandbox] = None

    @classmethod
    async def get_instance(cls) -> 'LocalSandboxClient':
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = create_sandbox_client()
        return cls._instance

    async def create(
        self,
        config: Optional[SandboxSettings] = None,
        volume_bindings: Optional[Dict[str, str]] = None,
    ) -> None:
        """Creates a sandbox.

        Args:
            config: Sandbox configuration.
            volume_bindings: Volume mappings.

        Raises:
            RuntimeError: If sandbox creation fails.
        """
        """Creates a sandbox with proper locking."""
        if self._lock is None:
            import asyncio
            self._lock = asyncio.Lock()

        async with self._lock:  # 使用异步锁确保并发安全
            if self.sandbox is not None:
                return  # 如果已经创建了，直接返回

        # Respect global configuration: if sandbox usage is disabled, skip creating a Docker sandbox.
        try:
            from app.config import config as _app_config

            use_sandbox = (
                (config.use_sandbox if config is not None else None)
                if hasattr(config, "use_sandbox")
                else None
            )
            # CLI override or provided config takes precedence; otherwise use global config
            if use_sandbox is None:
                use_sandbox = getattr(_app_config._config.sandbox, "use_sandbox", True)
        except Exception:
            # If we cannot access global config for some reason, default to enabling sandbox
            use_sandbox = True

        if not use_sandbox:
            logger.info("[DEBUG] Sandbox disabled by configuration — skipping Docker sandbox creation.")
            return

        logger.info("[DEBUG] Starting create docker sandbox...")
        self.sandbox = DockerSandbox(config, volume_bindings)
        await self.sandbox.create()

    async def run_command(self, command: str, timeout: Optional[int] = None) -> str:
        """Runs command in sandbox.

        Args:
            command: Command to execute.
            timeout: Execution timeout in seconds.

        Returns:
            Command output.

        Raises:
            RuntimeError: If sandbox not initialized.
        """
        if not self.sandbox:
            raise RuntimeError("Sandbox not initialized")
        return await self.sandbox.run_command(command, timeout)

    async def copy_from(self, container_path: str, local_path: str) -> None:
        """Copies file from container to local.

        Args:
            container_path: File path in container.
            local_path: Local destination path.

        Raises:
            RuntimeError: If sandbox not initialized.
        """
        if not self.sandbox:
            raise RuntimeError("Sandbox not initialized")
        await self.sandbox.copy_from(container_path, local_path)

    async def copy_to(self, local_path: str, container_path: str) -> None:
        """Copies file from local to container.

        Args:
            local_path: Local source file path.
            container_path: Destination path in container.

        Raises:
            RuntimeError: If sandbox not initialized.
        """
        if not self.sandbox:
            raise RuntimeError("Sandbox not initialized")
        await self.sandbox.copy_to(local_path, container_path)

    async def read_file(self, path: str) -> str:
        """Reads file from container.

        Args:
            path: File path in container.

        Returns:
            File content.

        Raises:
            RuntimeError: If sandbox not initialized.
        """
        if not self.sandbox:
            raise RuntimeError("Sandbox not initialized")
        return await self.sandbox.read_file(path)

    async def write_file(self, path: str, content: str) -> None:
        """Writes file to container.

        Args:
            path: File path in container.
            content: File content.

        Raises:
            RuntimeError: If sandbox not initialized.
        """
        if not self.sandbox:
            raise RuntimeError("Sandbox not initialized")
        await self.sandbox.write_file(path, content)

    async def cleanup(self) -> None:
        """Cleans up resources."""
        if self.sandbox:
            await self.sandbox.cleanup()
            self.sandbox = None


class SharedSandboxClient(BaseSandboxClient):
    """支持共享sandbox的client。

    多个agent进程可以通过功能类型（tag）共享同一个sandbox实例。
    使用引用计数管理，当所有使用者释放后，sandbox会在空闲超时后自动清理。
    """

    def __init__(self, tag: str = "default"):
        """初始化共享sandbox client。

        Args:
            tag: Sandbox功能类型标签（如"python_execute", "file_ops"等）
        """
        self.tag = tag
        self.sandbox: Optional[DockerSandbox] = None
        self.sandbox_id: Optional[str] = None
        self._pool = get_shared_pool()

    async def create(
        self,
        config: Optional[SandboxSettings] = None,
        volume_bindings: Optional[Dict[str, str]] = None,
    ) -> None:
        """从共享池获取或创建sandbox。

        Args:
            config: Sandbox配置
            volume_bindings: Volume映射配置

        Raises:
            RuntimeError: 如果获取或创建失败
        """
        # 检查配置是否启用sandbox
        try:
            from app.config import config as _app_config

            use_sandbox = (
                (config.use_sandbox if config is not None else None)
                if hasattr(config, "use_sandbox")
                else None
            )
            if use_sandbox is None:
                use_sandbox = getattr(_app_config._config.sandbox, "use_sandbox", True)
        except Exception:
            use_sandbox = True

        if not use_sandbox:
            logger.info(f"[DEBUG] Sandbox disabled by configuration for tag '{self.tag}'")
            return

        # 如果已经获取了sandbox，直接返回
        if self.sandbox is not None:
            return

        # 从共享池获取或创建sandbox
        logger.info(f"[DEBUG] Acquiring shared sandbox for tag '{self.tag}'...")
        self.sandbox_id = await self._pool.acquire_sandbox(
            tag=self.tag,
            config=config,
            volume_bindings=volume_bindings,
        )
        self.sandbox = await self._pool.get_sandbox(self.sandbox_id)

        if self.sandbox is None:
            raise RuntimeError(f"Failed to get sandbox {self.sandbox_id} from pool")

        logger.info(f"[DEBUG] Acquired shared sandbox {self.sandbox_id} for tag '{self.tag}'")

    async def run_command(self, command: str, timeout: Optional[int] = None) -> str:
        """在sandbox中执行命令。

        Args:
            command: 要执行的命令
            timeout: 执行超时时间（秒）

        Returns:
            命令输出

        Raises:
            RuntimeError: 如果sandbox未初始化
        """
        if not self.sandbox:
            raise RuntimeError("Sandbox not initialized")
        return await self.sandbox.run_command(command, timeout)

    async def copy_from(self, container_path: str, local_path: str) -> None:
        """从容器复制文件到本地。

        Args:
            container_path: 容器中的文件路径
            local_path: 本地目标路径

        Raises:
            RuntimeError: 如果sandbox未初始化
        """
        if not self.sandbox:
            raise RuntimeError("Sandbox not initialized")
        await self.sandbox.copy_from(container_path, local_path)

    async def copy_to(self, local_path: str, container_path: str) -> None:
        """从本地复制文件到容器。

        Args:
            local_path: 本地源文件路径
            container_path: 容器中的目标路径

        Raises:
            RuntimeError: 如果sandbox未初始化
        """
        if not self.sandbox:
            raise RuntimeError("Sandbox not initialized")
        await self.sandbox.copy_to(local_path, container_path)

    async def read_file(self, path: str) -> str:
        """从容器读取文件。

        Args:
            path: 容器中的文件路径

        Returns:
            文件内容

        Raises:
            RuntimeError: 如果sandbox未初始化
        """
        if not self.sandbox:
            raise RuntimeError("Sandbox not initialized")
        return await self.sandbox.read_file(path)

    async def write_file(self, path: str, content: str) -> None:
        """向容器写入文件。

        Args:
            path: 容器中的文件路径
            content: 文件内容

        Raises:
            RuntimeError: 如果sandbox未初始化
        """
        if not self.sandbox:
            raise RuntimeError("Sandbox not initialized")
        await self.sandbox.write_file(path, content)

    async def cleanup(self) -> None:
        """释放sandbox引用。

        注意：这不会立即销毁sandbox，只是释放引用。
        当引用计数为0且空闲超时后，sandbox会被自动清理。
        """
        if self.sandbox_id:
            await self._pool.release_sandbox(self.sandbox_id)
            logger.info(f"[DEBUG] Released shared sandbox {self.sandbox_id} for tag '{self.tag}'")
            self.sandbox = None
            self.sandbox_id = None


def create_sandbox_client() -> LocalSandboxClient:
    """Creates a SINGLETON sandbox client.

    Returns:
        LocalSandboxClient: SINGLETON Sandbox client instance.
    """
    return LocalSandboxClient()


SANDBOX_CLIENT = create_sandbox_client()


def create_shared_sandbox_client(tag: str = "default") -> SharedSandboxClient:
    """创建支持共享sandbox的client。

    Args:
        tag: Sandbox功能类型标签（如"python_execute", "file_ops"等）

    Returns:
        SharedSandboxClient: 共享sandbox client实例
    """
    return SharedSandboxClient(tag=tag)


# 保留向后兼容的全局SANDBOX_CLIENT，但建议新代码使用共享sandbox client
# 注意：这个全局实例仍然使用LocalSandboxClient，不会共享
SANDBOX_CLIENT = create_sandbox_client()
