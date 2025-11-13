import re
import csv
import matplotlib.pyplot as plt
import numpy as np

# 输入日志文件
LOG_FILE = "/home/zhangsiyi/AgenticAI/OpenManus/test_perf/io/20251021124312.log"
CSV_FILE = "/home/zhangsiyi/AgenticAI/OpenManus/test_perf/io/sandbox_io_perf.csv"
PLT_FILE = "/home/zhangsiyi/AgenticAI/OpenManus/test_perf/io/sandbox_perf_bar.png"
PLT_STACKED = "/home/zhangsiyi/AgenticAI/OpenManus/test_perf/io/sandbox_perf_stacked.png"

# 用于提取数据的正则
pattern_size = re.compile(r"Testing write size ([\d.]+)([KMG]B)")
pattern_times = {
    "mkdir_time": re.compile(r"mkdir_time=([\d.]+)s"),
    "tar_prep_time": re.compile(r"tar_prep_time=([\d.]+)s"),
    "put_archive_time": re.compile(r"put_archive_time=([\d.]+)s"),
    "total_time": re.compile(r"total_write_time=([\d.]+)s"),
}

def parse_log(filepath):
    results = []
    current = {}

    def finalize():
        if current and all(k in current for k in ["file_size", "mkdir_time", "tar_prep_time", "put_archive_time", "total_time"]):
            results.append(current.copy())

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            # 检测新测试块开头
            m_size = pattern_size.search(line)
            if m_size:
                # 保存上一个测试
                finalize()
                size_val, size_unit = m_size.groups()
                current = {"file_size": f"{size_val}{size_unit}"}
                continue

            # 匹配各个阶段的时间
            for key, ptn in pattern_times.items():
                m = ptn.search(line)
                if m:
                    current[key] = float(m.group(1))
                    break

    # 保存最后一个
    finalize()
    return results


def save_csv(data, outfile):
    headers = ["file_size", "mkdir_time", "tar_prep_time", "put_archive_time", "total_time"]
    with open(outfile, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in data:
            writer.writerow({k: f"{row[k]:.6f}" if k != "file_size" else row[k] for k in headers})
    print(f"✅ 已写入 CSV: {outfile}")


def plot_data(data):
    sizes = [d["file_size"] for d in data]
    mkdir_times = [d["mkdir_time"] for d in data]
    tar_prep_times = [d["tar_prep_time"] for d in data]
    put_archive_times = [d["put_archive_time"] for d in data]
    total_times = [d["total_time"] for d in data]

    # ---------- 图 1：总写入时间 ----------
    plt.figure(figsize=(8, 4))
    # plt.bar(sizes, total_times, color="#4C72B0")
    bars = plt.bar(sizes, total_times, color="#4C72B0")
    plt.xlabel("File Size")
    plt.ylabel("Total Write Time (s)")
    plt.title("Sandbox Write Performance - Total Time")
    # 让 x 轴标签倾斜，避免互相遮挡
    plt.xticks(rotation=45)
    plt.grid(axis="y", linestyle="--", alpha=0.6)
    # 在每个柱子上方标注数值
    for bar in bars:
        height = bar.get_height()
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            height,
            f"{height:.3f}",          # 保留三位小数
            ha="center",
            va="bottom",
            fontsize=8,
        )
    plt.tight_layout()
    plt.savefig(PLT_FILE, dpi=200)
    print(f"✅ 已生成总耗时图: {PLT_FILE}")

    # ---------- 图 2：堆叠阶段耗时 ----------
    plt.figure(figsize=(8, 4))
    x = np.arange(len(sizes))
    bar1 = plt.bar(x, mkdir_times, label="mkdir_time")
    bar2 = plt.bar(x, tar_prep_times, bottom=mkdir_times, label="tar_prep_time")
    bar3 = plt.bar(x, put_archive_times, bottom=np.array(mkdir_times) + np.array(tar_prep_times), label="put_archive_time")
    # 将 x 轴标签设置为文件大小并倾斜显示以节省空间
    plt.xticks(x, sizes, rotation=45)
    plt.xlabel("File Size")
    plt.ylabel("Time (s)")
    plt.title("Sandbox Write Performance - Stage Breakdown")
    plt.legend()
    plt.grid(axis="y", linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(PLT_STACKED, dpi=200)
    plt.show()
    print(f"✅ 已生成阶段堆叠图: {PLT_STACKED}")


if __name__ == "__main__":
    data = parse_log(LOG_FILE)
    save_csv(data, CSV_FILE)
    plot_data(data)
    print("✅ 日志解析与可视化完成！")
