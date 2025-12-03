"""
独立的Sandbox Pool Manager服务

作为守护进程运行，负责管理跨进程的sandbox生命周期。
"""
import asyncio
import json
import os
import signal
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional

import docker

from app.logger import logger


class PoolManagerService:
    """独立的Pool Manager服务，负责管理跨进程的sandbox。

    作为守护进程运行，定期扫描注册表并清理过期的sandbox。
    """

    def __init__(
        self,
        registry_dir: Optional[Path] = None,
        idle_timeout: int = 3600,
        cleanup_interval: int = 300,
        pid_file: Optional[Path] = None,
    ):
        """初始化Pool Manager服务。

        Args:
            registry_dir: 注册表目录，如果为None则使用默认目录
            idle_timeout: Sandbox空闲超时时间（秒）
            cleanup_interval: 清理检查间隔（秒）
            pid_file: PID文件路径，用于标识Manager进程
        """
        self.idle_timeout = idle_timeout
        self.cleanup_interval = cleanup_interval

        # 注册表目录
        if registry_dir is None:
            self.registry_dir = Path(tempfile.gettempdir()) / "openmanus_sandbox_registry"
        else:
            self.registry_dir = registry_dir
        self.registry_dir.mkdir(parents=True, exist_ok=True)

        # PID文件
        if pid_file is None:
            self.pid_file = self.registry_dir / "manager.pid"
        else:
            self.pid_file = pid_file

        # Docker客户端
        self.docker_client = docker.from_env()

        # 运行标志
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None

    def is_running(self) -> bool:
        """检查Manager服务是否正在运行。"""
        if not self.pid_file.exists():
            return False

        try:
            with open(self.pid_file, 'r') as f:
                pid = int(f.read().strip())

            # 检查进程是否存在
            os.kill(pid, 0)  # 发送信号0，不实际发送，只检查进程是否存在
            return True
        except (OSError, ValueError):
            # 进程不存在或PID文件无效
            self.pid_file.unlink(missing_ok=True)
            return False

    def start(self) -> None:
        """启动Manager服务。"""
        if self.is_running():
            logger.warning("Pool Manager is already running")
            return

        # 写入PID文件
        with open(self.pid_file, 'w') as f:
            f.write(str(os.getpid()))

        self._running = True

        # 注册信号处理
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        logger.info(f"Pool Manager started (PID: {os.getpid()})")
        logger.info(f"Registry directory: {self.registry_dir}")
        logger.info(f"Cleanup interval: {self.cleanup_interval}s")
        logger.info(f"Idle timeout: {self.idle_timeout}s")

        # 运行清理循环
        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            logger.info("Pool Manager interrupted")
        finally:
            self.stop()

    def stop(self) -> None:
        """停止Manager服务。"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()

        if self.pid_file.exists():
            self.pid_file.unlink()

        logger.info("Pool Manager stopped")

    def _signal_handler(self, signum, frame):
        """信号处理函数。"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)

    async def _run(self) -> None:
        """运行Manager服务的主循环。"""
        while self._running:
            try:
                await self._cleanup_cycle()
            except Exception as e:
                logger.error(f"Error in cleanup cycle: {e}")

            await asyncio.sleep(self.cleanup_interval)

    async def _cleanup_cycle(self) -> None:
        """执行一次清理周期。"""
        logger.debug("Starting cleanup cycle...")
        current_time = time.time()
        cleaned_count = 0
        invalid_count = 0

        try:
            # 扫描所有注册文件
            for registry_file in self.registry_dir.glob("*.json"):
                # 跳过PID文件
                if registry_file.name == "manager.pid":
                    continue

                try:
                    with open(registry_file, 'r') as f:
                        registry_data = json.load(f)

                    sandbox_id = registry_data.get("sandbox_id")
                    container_id = registry_data.get("container_id")
                    tag = registry_data.get("tag")
                    last_used = registry_data.get("last_used", 0)

                    if not container_id or not tag:
                        # 无效的注册文件
                        logger.warning(f"Invalid registry file: {registry_file.name}")
                        registry_file.unlink(missing_ok=True)
                        invalid_count += 1
                        continue

                    # 检查是否过期
                    is_expired = current_time - last_used > self.idle_timeout

                    # 验证容器是否存在
                    container_exists = await self._verify_container_exists(container_id)

                    if not container_exists:
                        # 容器不存在，删除注册文件
                        logger.info(
                            f"Removing registry entry for non-existent container "
                            f"{container_id[:12]}... (tag: {tag})"
                        )
                        registry_file.unlink(missing_ok=True)
                        invalid_count += 1
                    elif is_expired:
                        # 容器过期，尝试清理
                        logger.info(
                            f"Cleaning up expired sandbox {sandbox_id[:12]}... "
                            f"(container: {container_id[:12]}..., tag: {tag})"
                        )
                        if await self._cleanup_container(container_id):
                            registry_file.unlink(missing_ok=True)
                            cleaned_count += 1
                        else:
                            logger.warning(f"Failed to cleanup container {container_id[:12]}...")

                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in registry file: {registry_file.name}")
                    registry_file.unlink(missing_ok=True)
                    invalid_count += 1
                except Exception as e:
                    logger.error(f"Error processing registry file {registry_file.name}: {e}")

            if cleaned_count > 0 or invalid_count > 0:
                logger.info(
                    f"Cleanup cycle completed: cleaned {cleaned_count} sandboxes, "
                    f"removed {invalid_count} invalid entries"
                )
            else:
                logger.debug("Cleanup cycle completed: no action needed")

        except Exception as e:
            logger.error(f"Error in cleanup cycle: {e}")

    async def _verify_container_exists(self, container_id: str) -> bool:
        """验证Docker容器是否存在且运行。"""
        try:
            container = self.docker_client.containers.get(container_id)
            container.reload()
            return container.status == "running"
        except docker.errors.NotFound:
            return False
        except Exception as e:
            logger.debug(f"Error verifying container {container_id[:12]}...: {e}")
            return False

    async def _cleanup_container(self, container_id: str) -> bool:
        """清理Docker容器。"""
        try:
            container = self.docker_client.containers.get(container_id)
            container.stop(timeout=5)
            container.remove(force=True)
            logger.info(f"Successfully cleaned up container {container_id[:12]}...")
            return True
        except docker.errors.NotFound:
            # 容器已经不存在
            return True
        except Exception as e:
            logger.warning(f"Failed to cleanup container {container_id[:12]}...: {e}")
            return False

    def get_stats(self) -> Dict:
        """获取统计信息。"""
        stats = {
            "running": self.is_running(),
            "registry_dir": str(self.registry_dir),
            "idle_timeout": self.idle_timeout,
            "cleanup_interval": self.cleanup_interval,
        }

        if self.is_running():
            try:
                with open(self.pid_file, 'r') as f:
                    stats["pid"] = int(f.read().strip())
            except Exception:
                pass

        # 统计注册表中的sandbox数量
        registry_count = 0
        try:
            for registry_file in self.registry_dir.glob("*.json"):
                if registry_file.name != "manager.pid":
                    registry_count += 1
            stats["registered_sandboxes"] = registry_count
        except Exception:
            pass

        return stats


def main():
    """Pool Manager的主入口。"""
    import argparse

    parser = argparse.ArgumentParser(description="OpenManus Sandbox Pool Manager")
    parser.add_argument(
        "--idle-timeout",
        type=int,
        default=3600,
        help="Idle timeout in seconds (default: 3600)",
    )
    parser.add_argument(
        "--cleanup-interval",
        type=int,
        default=300,
        help="Cleanup interval in seconds (default: 300)",
    )
    parser.add_argument(
        "--registry-dir",
        type=str,
        default=None,
        help="Registry directory path (default: system temp)",
    )
    parser.add_argument(
        "--pid-file",
        type=str,
        default=None,
        help="PID file path (default: registry_dir/manager.pid)",
    )

    args = parser.parse_args()

    registry_dir = Path(args.registry_dir) if args.registry_dir else None
    pid_file = Path(args.pid_file) if args.pid_file else None

    manager = PoolManagerService(
        registry_dir=registry_dir,
        idle_timeout=args.idle_timeout,
        cleanup_interval=args.cleanup_interval,
        pid_file=pid_file,
    )

    manager.start()


if __name__ == "__main__":
    main()

