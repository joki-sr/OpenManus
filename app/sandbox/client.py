from abc import ABC, abstractmethod
from typing import Dict, Optional, Protocol

from app.config import SandboxSettings
from app.sandbox.core.sandbox import DockerSandbox
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


def create_sandbox_client() -> LocalSandboxClient:
    """Creates a SINGLETON sandbox client.

    Returns:
        LocalSandboxClient: SINGLETON Sandbox client instance.
    """
    return LocalSandboxClient()


SANDBOX_CLIENT = create_sandbox_client()
