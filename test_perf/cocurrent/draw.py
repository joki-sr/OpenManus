import os

import matplotlib.pyplot as plt
import pandas as pd

# ---------------------- 配置参数（按需修改）----------------------
CSV_PATH = "/mnt/e/Development/AgentAI/OpenManus/test_perf/cocurrent/data/20251120185649_10.csv"  # 你的CSV文件路径
csv_filename = os.path.splitext(os.path.basename(CSV_PATH))[0]  # 结果：20251118165602_1
OUTPUT_IMG = f"/mnt/e/Development/AgentAI/OpenManus/test_perf/cocurrent/data/{csv_filename}.png"  # 最终图片路径
FIG_SIZE = (12, 6)  # 图表尺寸（宽，高）
DPI = 150  # 图片清晰度（越高越清晰）
# ----------------------------------------------------------------

# 1. 读取CSV数据（处理可能的编码问题）
try:
    df = pd.read_csv(CSV_PATH, encoding="utf-8")
except UnicodeDecodeError:
    df = pd.read_csv(CSV_PATH, encoding="gbk")

# 2. 数据预处理（确保列名匹配，过滤异常值）
df = df[["time_s", "cpu_percent", "memory_mb"]].dropna()  # 只保留目标列，删除空值
df = df[df["time_s"] >= 0]  # 过滤负时间（异常数据）

# 3. 创建图表和双纵轴
fig, ax1 = plt.subplots(figsize=FIG_SIZE, dpi=DPI)

# 4. 左纵轴：CPU使用率（蓝色线）
color1 = "#2E86AB"  # 蓝色
ax1.set_xlabel("time (s)", fontsize=12)
ax1.set_ylabel("CPU utilization (%)", color=color1, fontsize=12)
line1 = ax1.plot(df["time_s"], df["cpu_percent"], color=color1, linewidth=2, label="CPU utilization", marker="o", markersize=3)
ax1.tick_params(axis="y", labelcolor=color1)
ax1.grid(alpha=0.3)  # 网格线（透明度0.3，不干扰视线）

# 5. 右纵轴：内存占用（橙色线）
ax2 = ax1.twinx()  # 共享横轴，创建第二个纵轴
color2 = "#A23B72"  # 橙色
ax2.set_ylabel("Memory usage (MB)", color=color2, fontsize=12)
line2 = ax2.plot(df["time_s"], df["memory_mb"], color=color2, linewidth=2, label="Memory usage", marker="s", markersize=3)
ax2.tick_params(axis="y", labelcolor=color2)

# 6. 合并图例（同时显示两条线的标签）
lines = line1 + line2
labels = [l.get_label() for l in lines]
ax1.legend(lines, labels, loc="upper left", fontsize=10)

# 7. 标题和布局调整
plt.title("Agent concurrent tasks - CPU utilization & memory usage trends", fontsize=14, pad=20)
plt.tight_layout()  # 自动调整布局，避免标签被截断

# 8. 保存图片（支持PNG/JPG/PDF格式）
plt.savefig(OUTPUT_IMG, bbox_inches="tight", dpi=DPI)
plt.close()

print(f"图表已保存到：\n{os.path.abspath(OUTPUT_IMG)}")
print(f"图表信息：时间范围 {df['time_s'].min():.1f}s - {df['time_s'].max():.1f}s")
print(f"峰值 CPU：{df['cpu_percent'].max():.1f}% | 峰值内存：{df['memory_mb'].max():.1f}MB")
