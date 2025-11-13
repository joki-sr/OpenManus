import asyncio
import os
import sys
import time
from pathlib import Path
from statistics import mean, stdev
from typing import List, Tuple, Dict
import matplotlib.pyplot as plt
import numpy as np
import re

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.config import SandboxSettings
from app.sandbox.core.sandbox import DockerSandbox


config = SandboxSettings()
sandbox = DockerSandbox(config)
# sandbox.create()


SIZES = [1024, #1kb
         4 * 1024,
          8 * 1024,
          16 * 1024,
          256 * 1024,
          1 * 1024 * 1024,
          4 * 1024 * 1024,
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


def plot_write_times(sizes: List[int], all_times: List[float]):
    """Plot bar chart of write times for different file sizes."""
    fig, ax = plt.subplots(figsize=(12, 6))

    # Convert sizes to human readable format for x-axis
    x_labels = [human_size(s) for s in sizes]

    # Create the bar chart
    ax.bar(x_labels, all_times, color='#2ecc71')

    ax.set_title('File Write Times by Size')
    ax.set_xlabel('File Size')
    ax.set_ylabel('Time (seconds)')
    plt.xticks(rotation=45)

    # Add value labels on top of each bar
    for i, v in enumerate(all_times):
        ax.text(i, v, f'{v:.3f}s', ha='center', va='bottom')

    plt.tight_layout()
    plt.savefig('sandbox_write_times.png')
    print("\nVisualization saved as sandbox_write_times.png")


async def main():
    await sandbox.create()
    iterations = 1
    print(f"Starting sandbox IO performance test: sizes={', '.join(human_size(s) for s in SIZES)} iterations={iterations}\n")

    all_times = []

    for size in SIZES:
        print(f"Testing write size {human_size(size)} ({size} bytes)")
        try:
            times = await measure_write_per_size(size, iterations, config)
            label = f"{human_size(size)} write"
            print_stats(label, times)
            # Store the average time for visualization
            all_times.append(mean(times))
        except Exception as e:
            print(f"Error testing size {size}: {e}")
            all_times.append(0)  # Use 0 for failed tests

    # Plot the results
    plot_write_times(SIZES, all_times)    # await sandbox.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
