import time
import subprocess
import os
from pathlib import Path

def run_agent(prompt):
    """启动 agent 并执行 prompt"""
    start = time.time()
    proc = subprocess.run(
        ["python", "main.py"],
        input=prompt,
        text=True,
        capture_output=True,
        timeout=600  # 防止超大任务卡死
    )
    duration = time.time() - start
    return {
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
        "duration": duration,
    }

def collect_file_info(test_dir):
    """统计测试目录中实际生成的文件信息"""
    info = []
    for f in Path(test_dir).glob("*"):
        if f.is_file():
            size = f.stat().st_size
            info.append((f.name, size))
    return info

def test_sandbox():
    os.makedirs("test_perf", exist_ok=True)
    test_dir = "sandbox_files"
    os.makedirs(test_dir, exist_ok=True)

    # 文件大小规格（单位字节）
    size_map = {
        "1KB": 1024,
        # "4KB": 4 * 1024,
        # "8KB": 8 * 1024,
        # "16KB": 16 * 1024,
        # "256KB": 256 * 1024,
        # "1MB": 1 * 1024 * 1024,
        # "4MB": 4 * 1024 * 1024,
    }

    tasks = []
    for name, size in size_map.items():
        # 构造 prompt：让 LLM 生成并执行 Python 代码，写入指定大小文件
        prompt = f"你是一个能够执行 Python 代码的 AI Agent。请生成并执行一段 Python 代码，完成以下任务 1. 在当前工作目录下创建文件 {test_dir}/file_{name}.txt, 2. 文件内容可以是重复的随机字符, 3. 文件大小大约为 {size} 字节, 4. 输出完成后打印'写入完成：{name}' "

        tasks.append((name, prompt.strip()))

    # 循环执行每个测试任务
    for name, prompt in tasks:
        print(f"[Running test] 写入 {name} 文件...")
        result = run_agent(prompt)
        file_info = collect_file_info(test_dir)

        # 输出测试结果
        report_path = f"test_perf/test_{name}_sandbox.txt"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"=== Test: {name} ===\n")
            f.write(f"Prompt:\n{prompt}\n")
            f.write(f"\n--- STDOUT ---\n{result['stdout']}\n")
            f.write(f"\n--- STDERR ---\n{result['stderr']}\n")
            f.write(f"\n--- RETURN CODE --- {result['returncode']}\n")
            f.write(f"--- DURATION --- {result['duration']:.3f}s\n\n")

            f.write("--- Generated Files ---\n")
            for fname, size in file_info:
                f.write(f"{fname}\t{size} bytes\n")

        print(f"✅ 结果已保存：{report_path}")

if __name__ == "__main__":
    test_sandbox()
