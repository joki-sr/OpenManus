"""
Docker Sandbox Module

Provides secure containerized execution environment with resource limits
and isolation for running untrusted code.
"""
from app.sandbox.client import (
    BaseSandboxClient,
    LocalSandboxClient,
    SharedSandboxClient,
    create_sandbox_client,
    create_shared_sandbox_client,
)
from app.sandbox.core.shared_pool import SharedSandboxPool, get_shared_pool
from app.sandbox.core.exceptions import (
    SandboxError,
    SandboxResourceError,
    SandboxTimeoutError,
)
from app.sandbox.core.manager import SandboxManager
from app.sandbox.core.sandbox import DockerSandbox


__all__ = [
    "DockerSandbox",
    "SandboxManager",
    "BaseSandboxClient",
    "LocalSandboxClient",
    "SharedSandboxClient",
    "SharedSandboxPool",
    "create_sandbox_client",
    "create_shared_sandbox_client",
    "get_shared_pool",
    "SandboxError",
    "SandboxTimeoutError",
    "SandboxResourceError",
]
