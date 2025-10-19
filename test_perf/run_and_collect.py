import subprocess
import time
import os
import json
import re
from typing import Dict, Any

try:
    import psutil
except Exception:
    psutil = None

OUTPUT_DIR = "test_perf/results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TASKS = [
    ("file_write_single", "请创建 test.txt 并写入 hello"),
    ("file_write_batch", "请创建20个 test1.txt,...,test20.txt 并写入 hello1,...,hello20"),
    ("file_write_read", "请创建20个 test1.txt,...,test20.txt 并写入 hello1,...,hello20，然后依次cat每个文件的内容"),
    ("info_retrieval", "请访问关于人工智能的网页资料，并总结"),
]

TOKEN_USAGE_RE = re.compile(r"Token usage: (.*)")
SANDBOX_CREATE_RE = re.compile(r"Starting Docker sandbox creation")
TOOL_CALL_RE = re.compile(r"Activating tool: '([\w_\-]+)'")


def parse_metrics_from_log(text: str) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    # sandbox creation count
    metrics["sandbox_creation_count"] = len(SANDBOX_CREATE_RE.findall(text))

    # tools called
    metrics["tools_called"] = TOOL_CALL_RE.findall(text)

    # token usage - take last occurrence
    tu = TOKEN_USAGE_RE.findall(text)
    if tu:
        last = tu[-1]
        parts = [p.strip() for p in last.split(",")]
        token_map = {}
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                try:
                    token_map[k.strip()] = int(v)
                except Exception:
                    token_map[k.strip()] = v.strip()
        metrics["token_usage"] = token_map
    else:
        metrics["token_usage"] = None

    return metrics


def capture_process_snapshot(pid: int) -> Dict[str, Any]:
    if not psutil:
        return {}
    try:
        p = psutil.Process(pid)
        with p.oneshot():
            mem = p.memory_info()._asdict()
            cpu = p.cpu_times()._asdict()
            io = p.io_counters()._asdict() if p.is_running() else {}
            return {"memory": mem, "cpu_times": cpu, "io": io}
    except Exception:
        return {}


def run_prompt(prompt: str, timeout: int = 300) -> Dict[str, Any]:
    # run main.py and provide prompt via stdin
    start = time.time()
    proc = subprocess.run(["python", "main.py"], input=prompt, text=True, capture_output=True)
    duration = time.time() - start

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    combined = stdout + "\n" + stderr

    metrics = parse_metrics_from_log(combined)
    metrics.update({
        "duration": duration,
        "returncode": proc.returncode,
    })

    return {
        "stdout": stdout,
        "stderr": stderr,
        "metrics": metrics,
    }


if __name__ == "__main__":
    mode = os.environ.get("TEST_MODE", "sandbox")  # user can set env to 'nosandbox' to indicate mode
    for name, prompt in TASKS:
        print(f"Running {name} (mode={mode})...")
        res = run_prompt(prompt)
        outname = f"{name}_{mode}"
        json_path = os.path.join(OUTPUT_DIR, outname + ".json")
        txt_path = os.path.join(OUTPUT_DIR, outname + ".txt")
        with open(json_path, "w") as f:
            json.dump(res["metrics"], f, indent=2)
        with open(txt_path, "w") as f:
            f.write("== STDOUT ==\n")
            f.write(res["stdout"] + "\n")
            f.write("== STDERR ==\n")
            f.write(res["stderr"] + "\n")
            f.write("== METRICS ==\n")
            json.dump(res["metrics"], f, indent=2)
        print(f"Saved: {json_path}, {txt_path}")
