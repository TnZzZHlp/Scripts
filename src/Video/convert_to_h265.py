#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将视频文件转码为H.265编码。
用法: python convert_to_h265.py <视频文件路径>
"""

import argparse
import os
import subprocess
import sys


def convert_to_h265(input_file):
    """
    使用ffmpeg将视频转码为H.265格式

    参数:
        input_file: 输入视频文件路径
    """
    # 检查文件是否存在
    if not os.path.isfile(input_file):
        print(f"错误: 文件不存在 - {input_file}")
        return False

    # 构建输出文件路径
    file_dir = os.path.dirname(input_file)
    file_name, file_ext = os.path.splitext(os.path.basename(input_file))
    output_file = os.path.join(file_dir, f"{file_name}_h265{file_ext}")

    # 构建ffmpeg命令
    ffmpeg_cmd = [
        "ffmpeg",
        "-i",
        input_file,
        "-preset",
        "fast",  # 或 "faster", "veryfast"
        "-c:v",
        "hevc_qsv",
        "-c:v",
        "libx265",  # 视频编码器设为H.265
        "-crf",
        "23",  # 恒定速率因子 - 控制质量 (低值=高质量)
        "-preset",
        "medium",  # 编码速度预设
        "-c:a",
        "copy",  # 复制音频流
        "-c:s",
        "copy",  # 复制字幕流 (如果有)
        output_file,
    ]

    print(f"正在转码: {input_file}")
    print(f"输出文件: {output_file}")
    print("转码中，请稍候...")

    try:
        # 执行ffmpeg命令
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )

        # 安全地处理并显示进度信息
        if process.stdout:  # 确保stdout不是None
            for line in process.stdout:
                # 仅显示包含关键字的行以减少输出量
                if "frame=" in line or "speed=" in line or "error" in line.lower():
                    print(f"\r{line.strip()}", end="")

                    # 如果用户需要了解转码速度，可以取消下面注释
                    # if "speed=" in line:
                    #     explain_encoding_speed(line)
        else:
            # 如果无法获取输出流，提供一个替代方案
            print("正在处理中，请等待...")

        # 等待进程完成
        return_code = process.wait()

        if return_code == 0:
            print(f"\n\n转码完成！输出文件: {output_file}")
            print(f"原始文件大小: {os.path.getsize(input_file) / (1024*1024):.2f} MB")
            print(
                f"转码后文件大小: {os.path.getsize(output_file) / (1024*1024):.2f} MB"
            )
            return True
        else:
            print(f"\n转码失败，ffmpeg返回错误代码: {return_code}")
            return False

    except FileNotFoundError:
        print("错误: 找不到ffmpeg。请确保ffmpeg已安装并添加到系统PATH中。")
        return False
    except Exception as e:
        print(f"发生错误: {str(e)}")
        return False


def explain_encoding_speed(progress_line):
    """解释FFmpeg的转码速度"""
    try:
        # 尝试从输出行中提取速度值
        speed_part = progress_line.split("speed=")[1].split(" ")[0]
        speed_value = float(speed_part.replace("x", ""))

        print("\n\n转码速度分析:")
        print(f"当前速度: {speed_value}x (实时速度的{speed_value*100:.1f}%)")

        if speed_value < 0.2:
            print(
                "这是一个较慢的转码速度。处理1分钟视频需要约{:.1f}分钟。".format(
                    1 / speed_value
                )
            )
            print("\n提升速度的建议:")
            print("1. 使用更快的预设: 将-preset参数从'medium'改为'faster'或'fast'")
            print("2. 增加CRF值(降低质量): 将-crf参数从23改为26-28")
            print("3. 如果硬件支持，启用硬件加速转码:")
            print("   - 对于NVIDIA GPU: 使用-c:v hevc_nvenc")
            print("   - 对于Intel GPU: 使用-c:v hevc_qsv")
            print("   - 对于AMD GPU: 使用-c:v hevc_amf")
            print("4. 减小输出分辨率: 添加-vf scale=1280:-1参数")
        elif speed_value < 0.5:
            print("这是一个中等的转码速度。")
        else:
            print("这是一个较好的转码速度。")
    except:
        pass  # 如果解析失败，不显示额外信息


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将视频转码为H.265格式")
    parser.add_argument("input_file", help="输入视频文件路径")

    args = parser.parse_args()
    convert_to_h265(args.input_file)  # 移除了多余的命令行参数检查，argparse会自动处理
