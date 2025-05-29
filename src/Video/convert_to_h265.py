#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将视频文件转码为H.265编码。
用法: python convert_to_h265.py <视频文件路径> [--intel] [--amd] [--nvidia]
使用 --intel 参数启用 Intel QuickSync 硬件加速
使用 --amd 参数启用 AMD AMF 硬件加速
使用 --nvidia 参数启用 NVIDIA NVENC 硬件加速
"""

import argparse
import os
import subprocess
import sys


def convert_to_h265(input_file, use_intel=False, use_amd=False, use_nvidia=False):
    """
    使用ffmpeg将视频转码为H.265格式

    参数:
        input_file: 输入视频文件路径
        use_intel: 是否使用Intel QuickSync硬件加速
        use_amd: 是否使用AMD AMF硬件加速
        use_nvidia: 是否使用NVIDIA NVENC硬件加速
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
    ]

    # 硬件加速选择
    if use_intel:
        # Intel QuickSync
        ffmpeg_cmd.extend(
            [
                "-c:v",
                "hevc_qsv",  # Intel QuickSync HEVC/H.265编码器
                "-preset",
                "fast",  # 编码速度预设
                "-load_plugin",
                "hevc_hw",  # 加载HEVC硬件编码插件
            ]
        )
    elif use_amd:
        # AMD AMF
        ffmpeg_cmd.extend(
            [
                "-c:v",
                "hevc_amf",  # AMD HEVC/H.265编码器
                "-quality",
                "balanced",  # 质量设置
            ]
        )
    elif use_nvidia:
        # NVIDIA NVENC
        ffmpeg_cmd.extend(
            [
                "-c:v",
                "hevc_nvenc",  # NVIDIA NVENC H.265编码器
                "-preset",
                "fast",  # NVENC编码预设
                "-cq",
                "23",  # 恒定质量
            ]
        )
    else:
        # 软件 x265
        ffmpeg_cmd.extend(
            [
                "-c:v",
                "libx265",  # 软件x265编码器
                "-crf",
                "23",  # 质量控制参数 (对应于CRF)
                "-preset",
                "medium",  # 编码速度预设
            ]
        )

    # 添加通用的编码参数
    ffmpeg_cmd.extend(
        [
            "-c:a",
            "copy",  # 复制音频流
            "-c:s",
            "copy",  # 复制字幕流 (如果有)
            output_file,
        ]
    )

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将视频转码为H.265格式")
    parser.add_argument("input_file", help="输入视频文件路径")
    parser.add_argument(
        "--intel",
        action="store_true",
        help="使用 Intel QuickSync硬件加速",
    )
    parser.add_argument(
        "--amd",
        action="store_true",
        help="使用 AMD GPU 硬件加速",
    )
    parser.add_argument(
        "--nvidia",
        action="store_true",
        help="使用 NVIDIA NVENC 硬件加速",
    )

    args = parser.parse_args()
    if sum(bool(x) for x in (args.intel, args.amd, args.nvidia)) > 1:
        print("错误: 只能指定其中一个硬件加速选项")
        sys.exit(1)

    convert_to_h265(
        args.input_file,
        use_intel=args.intel,
        use_amd=args.amd,
        use_nvidia=args.nvidia,
    )
