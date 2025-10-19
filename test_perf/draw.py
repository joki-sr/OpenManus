import pandas as pd
import plotly.figure_factory as ff
from datetime import datetime
import re

def parse_log_events(log_content):
    events = []

    # 正则表达式匹配时间戳和事件描述
    pattern = r'(\d{2}:\d{2}:\d{2}\.\d{3}).+?(?:DEBUG|INFO).+?(Starting|Finish|Executing|Token usage|Activating|completed).+?'

    matches = re.finditer(pattern, log_content, re.MULTILINE)

    base_time = None
    for match in matches:
        timestamp_str = match.group(1)
        event_desc = match.group(2)

        # 解析时间
        timestamp = datetime.strptime(timestamp_str, '%H:%M:%S.%f')

        if base_time is None:
            base_time = timestamp

        # 计算相对时间（秒）
        relative_time = (timestamp - base_time).total_seconds()

        events.append({
            'Task': event_desc,
            'Start': relative_time,
            'Finish': relative_time + 0.1,  # 为了显示效果，给每个事件一个短暂持续时间
            'Description': event_desc
        })

    return events, base_time

def create_timeline(log_file_path):
    # 读取日志文件
    with open(log_file_path, 'r') as f:
        log_content = f.read()

    # 解析事件
    events, base_time = parse_log_events(log_content)

    # 创建DataFrame
    df = pd.DataFrame(events)

    # 先更新事件的Task分类
    for event in events:
        if 'Initializing' in event['Description']:
            event['Task'] = 'Starting'
        elif 'sandbox' in event['Description'].lower():
            event['Task'] = 'Sandbox'
        elif 'Token usage' in event['Description']:
            event['Task'] = 'Token'
        elif 'Executing' in event['Description']:
            event['Task'] = 'Executing'
        elif 'Activating' in event['Description']:
            event['Task'] = 'Tool'
        elif 'completed' in event['Description']:
            event['Task'] = 'Finish'
        else:
            event['Task'] = 'Other'

    # 创建DataFrame后获取实际的Task类型
    df = pd.DataFrame(events)
    unique_tasks = df['Task'].unique()

    # 定义颜色映射
    colors = {
        task: f'rgb({hash(task) % 200}, {(hash(task) >> 8) % 200}, {(hash(task) >> 16) % 200})'
        for task in unique_tasks
    }

    # 创建甘特图
    fig = ff.create_gantt(df,
                         colors=colors,
                         index_col='Task',  # 使用Task而不是Description作为索引
                         group_tasks=True,
                         show_colorbar=True,
                         showgrid_x=True,
                         showgrid_y=True)

    # 更新布局
    fig.update_layout(
        title={
            'text': 'OpenManus Agent Event Timeline',
            'y':0.95,
            'x':0.5,
            'xanchor': 'center',
            'yanchor': 'top'
        },
        xaxis_title='Time (seconds from start)',
        height=800,
        font=dict(size=12),
        showlegend=True,
        barmode='overlay',
        bargap=0.15,
        plot_bgcolor='white',
        paper_bgcolor='white',
    )

    # 添加网格线
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')

    # 保存为HTML文件（交互式）
    fig.write_html("timeline.html")

    # 保存为静态图片
    fig.write_image("timeline.png")

# 使用示例
log_file_path = "/home/zhangsiyi/AgenticAI/OpenManus/test_perf/文件写入_sandbox.txt"
create_timeline(log_file_path)

exit(0)

#------------------------------------------------------------------------------
def analyze_performance(log_content):
    # 分析各个阶段的耗时
    stages = {
        'initialization': (r'Initializing.*?Daytona client initialized', 'Initialization'),
        'sandbox_creation': (r'Starting Docker sandbox.*?Finish Docker sandbox.*?creation', 'Sandbox Creation'),
        'llm_thinking': (r'Executing step.*?Token usage', 'LLM Thinking'),
        'tool_execution': (r'Activating tool.*?completed its mission', 'Tool Execution')
    }

    metrics = {}
    for stage_name, (pattern, label) in stages.items():
        matches = re.finditer(pattern, log_content, re.DOTALL)
        durations = []
        for match in matches:
            # 提取时间戳并计算持续时间
            timestamps = re.findall(r'(\d{2}:\d{2}:\d{2}\.\d{3})', match.group(0))
            if len(timestamps) >= 2:
                start = datetime.strptime(timestamps[0], '%H:%M:%S.%f')
                end = datetime.strptime(timestamps[-1], '%H:%M:%S.%f')
                duration = (end - start).total_seconds()
                durations.append(duration)

        metrics[stage_name] = {
            'count': len(durations),
            'total_duration': sum(durations),
            'avg_duration': sum(durations)/len(durations) if durations else 0
        }

    return metrics

# 分析性能数据
with open(log_file_path, 'r') as f:
    log_content = f.read()
metrics = analyze_performance(log_content)

# 打印分析结果
for stage, data in metrics.items():
    print(f"\n{stage.replace('_', ' ').title()}:")
    print(f"  Count: {data['count']}")
    print(f"  Total Duration: {data['total_duration']:.3f}s")
    print(f"  Average Duration: {data['avg_duration']:.3f}s")
