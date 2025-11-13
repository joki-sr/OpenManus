import time
import subprocess
import os

def run_agent(prompt):
    # 启动 agent
    start = time.time()
    proc = subprocess.run(["python", "main.py"], input=prompt, text=True, capture_output=True)
    duration = time.time() - start
    return {
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
        "duration": duration,
    }

def test_sandbox():
    # os.makedirs("test_perf", exist_ok=True)
    tasks = [
        # ("文件写入", "请使用工具str_replace_editor而不是python脚本工具，创建文件。创建的文件要求：1个文件，命名： test.txt 并分别写入 hello"),
        ("批量文件写入", "请使用工具str_replace_editor,不允许用python脚本工具，创建文件。创建的文件要求：10个文件，命名： test1.txt, test2.txt,... 并分别写入 hello1,hello2,..."),
        # ("文件写+读", "请使用工具str_replace_editor而不是python脚本工具，创建文件。创建的文件要求：10个文件，命名： test1.txt, test2.txt,... 并分别写入 hello1,hello2,...,并且每写完一个文件就要cat每个文件的内容"),
        # ("信息检索", "请访问关于人工智能的网页资料，并总结个ai_review.txt文件"),
    ]

    # 当前是 sandbox 模式测试
    for name, prompt in tasks:
        result = run_agent(prompt)
        with open(f"test_perf/{name}_sandbox.txt", "w") as f:
            f.write(result["stdout"])
            f.write("\n---stderr---\n")
            f.write(result["stderr"])
            f.write(f"\n---returncode---\n{result['returncode']}\n---duration---\n{result['duration']}\n")

if __name__ == '__main__':
    test_sandbox()
