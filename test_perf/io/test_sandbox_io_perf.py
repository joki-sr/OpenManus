import asyncio
import os
import sys
import time
from pathlib import Path
from statistics import mean, stdev
from typing import List, Tuple

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from app.config import SandboxSettings
from app.sandbox.core.sandbox import DockerSandbox


config = SandboxSettings()
sandbox = DockerSandbox(config)
# sandbox.create()


# SIZES = [1024, #1kb
#          4 * 1024,
#           8 * 1024,
#           16 * 1024,
#           256 * 1024,
#           1 * 1024 * 1024,
#           4 * 1024 * 1024,
#           ]
SIZES = [
    1 * 1024,               # 1 KB
    4 * 1024,               # 4 KB
    8 * 1024,               # 8 KB
    16 * 1024,              # 16 KB
    32 * 1024,              # 32 KB
    64 * 1024,              # 64 KB
    128 * 1024,             # 128 KB
    256 * 1024,             # 256 KB
    512 * 1024,             # 512 KB
    1 * 1024 * 1024,        # 1 MB
    2 * 1024 * 1024,        # 2 MB
    4 * 1024 * 1024,        # 4 MB
    8 * 1024 * 1024,        # 8 MB
    16 * 1024 * 1024,       # 16 MB
    32 * 1024 * 1024,       # 32 MB
    64 * 1024 * 1024,       # 64 MB
    128 * 1024 * 1024,      # 128 MB
    256 * 1024 * 1024,      # 256 MB
]



def human_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024*1024):.2f}MB"
    if n >= 1024:
        return f"{n / 1024:.2f}KB"
    return f"{n}B"


async def measure_write_per_size(size: int, iterations: int, config: SandboxSettings) -> List[float]:
    """Measure write times for given size (bytes). Returns list of times."""
    times: List[float] = []

    # Prepare content buffer once
    content = b"A" * size

    for i in range(iterations):

        try:
            filename = f"/tmp/test_write_{size}_{i}.bin"
            t0 = time.time()
            # Use write_file which uses put_archive under the hood and run_command for mkdir
            await sandbox.write_file(filename, content.decode('latin1'))
            t1 = time.time()
            times.append(t1 - t0)

            # optional small read to ensure file exists (not timed)
            await sandbox.run_command(f"test -e {filename}")

        finally:
            # await sandbox.cleanup()
            # give a tiny pause to allow Docker to release resources
            await asyncio.sleep(0.2)

    return times


def print_stats(operation: str, times: List[float]) -> None:
    avg_time = mean(times) if times else 0
    std_time = stdev(times) if len(times) > 1 else 0
    min_time = min(times) if times else 0
    max_time = max(times) if times else 0

    print(f"{operation} Statistics:")
    print(f"  Size:        {operation.split()[0]}")
    print(f"  Average Time: {avg_time:.3f}s")
    print(f"  Std Dev:     {std_time:.3f}s")
    print(f"  Min Time:    {min_time:.3f}s")
    print(f"  Max Time:    {max_time:.3f}s")
    print(f"  All Times:   {', '.join(f'{t:.3f}' for t in times)}s")
    print()


async def main():
    await sandbox.create()
    iterations = 1
    print(f"Starting sandbox IO performance test: sizes={', '.join(human_size(s) for s in SIZES)} iterations={iterations}\n")

    # config = SandboxSettings()
    # sandbox = DockerSandbox(config)
    # await sandbox.create()

    for size in SIZES:
        print(f"Testing write size {human_size(size)} ({size} bytes)")
        try:
            times = await measure_write_per_size(size, iterations, config)
            label = f"{human_size(size)} write"
            print_stats(label, times)
        except Exception as e:
            print(f"Error testing size {size}: {e}")

    # await sandbox.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
