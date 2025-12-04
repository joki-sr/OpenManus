#!/usr/bin/env python3
"""
检查logs文件夹下所有.log文件的最后一行是否包含"Force exiting process..."
"""
import os
from pathlib import Path


def check_log_file(log_path):
    """检查单个log文件的最后一行是否包含指定内容"""
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            # 读取文件的最后一行
            # 对于大文件，从文件末尾读取更高效
            try:
                # 尝试读取最后一行（对于小文件）
                lines = f.readlines()
                if not lines:
                    return False, "文件为空"
                last_line = lines[-1].strip()
            except:
                # 如果文件太大，使用seek从末尾读取
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
                if file_size == 0:
                    return False, "文件为空"

                # 从文件末尾读取最后几KB
                read_size = min(4096, file_size)
                f.seek(max(0, file_size - read_size))
                lines = f.readlines()
                if not lines:
                    return False, "无法读取"
                last_line = lines[-1].strip()

            # 检查是否包含目标内容
            if "Force exiting process..." in last_line:
                return True, last_line
            else:
                return False, last_line
    except Exception as e:
        return None, f"读取错误: {str(e)}"


def main():
    """主函数"""
    logs_dir = Path("./logs")

    if not logs_dir.exists():
        print(f"错误: {logs_dir} 文件夹不存在")
        return

    # 获取所有.log文件
    log_files = sorted(logs_dir.glob("*.log"))

    if not log_files:
        print(f"在 {logs_dir} 文件夹下没有找到.log文件")
        return

    print(f"找到 {len(log_files)} 个.log文件\n")
    print("=" * 80)

    # 统计结果
    has_force_exit = []
    no_force_exit = []
    errors = []

    # 检查每个文件
    for log_file in log_files:
        result, info = check_log_file(log_file)
        file_name = log_file.name

        if result is True:
            has_force_exit.append(file_name)
            print(f"✓ {file_name}")
            print(f"  最后一行: {info[:100]}...")
        elif result is False:
            no_force_exit.append(file_name)
            print(f"✗ {file_name}")
            print(f"  最后一行: {info[:100]}...")
        else:
            errors.append((file_name, info))
            print(f"⚠ {file_name}")
            print(f"  错误: {info}")
        print()

    # 输出统计信息
    print("=" * 80)
    print("\n统计结果:")
    print(f"  包含 'Force exiting process...': {len(has_force_exit)} 个文件")
    print(f"  不包含 'Force exiting process...': {len(no_force_exit)} 个文件")
    print(f"  读取错误: {len(errors)} 个文件")

    if no_force_exit:
        print(f"\n不包含 'Force exiting process...' 的文件列表:")
        for f in no_force_exit:
            print(f"  - {f}")

    if errors:
        print(f"\n读取错误的文件列表:")
        for f, err in errors:
            print(f"  - {f}: {err}")


if __name__ == "__main__":
    main()

