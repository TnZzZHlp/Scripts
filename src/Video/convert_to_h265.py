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


def convert_to_h265(
    input_file,
    use_intel=False,
    use_amd=False,
    use_nvidia=False,
    crf=23,
    preset="medium",
    bitrate=None,
):
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

    # 将 Windows 路径反斜杠改为正斜杠，避免 \0 被误识别
    input_file = input_file.replace("\\", "/")
    output_file = output_file.replace("\\", "/")

    # 构建 ffmpeg 命令
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",  # 如果目标已存在则强制覆盖
        "-i",
        input_file,
    ]

    # 硬件／软件编码选择
    if use_intel:
        ffmpeg_cmd.extend(
            [
                "-c:v",
                "hevc_qsv",  # Intel QuickSync HEVC/H.265编码器
                "-global_quality",
                str(crf),  # QSV 对应的质量参数
                "-preset",
                preset,
            ]
        )
    elif use_amd:
        # 将 --preset 映射到 AMF 的 quality 参数
        amf_quality = {
            "ultrafast": "speed",
            "fast": "speed",
            "medium": "balanced",
            "slow": "quality",
            "slower": "quality",
            "veryslow": "quality",
        }.get(preset, "balanced")

        ffmpeg_cmd.extend(
            [
                "-c:v",
                "hevc_amf",  # AMD HEVC/H.265编码器
                "-rc",
                "cqp",  # AMF 使用 CQP 模式
                "-qp",
                str(crf),  # AMF 的质量参数
                "-quality",
                amf_quality,  # AMF 支持的 quality 选项
            ]
        )
    elif use_nvidia:
        ffmpeg_cmd.extend(
            [
                "-c:v",
                "hevc_nvenc",  # NVIDIA NVENC H.265编码器
                "-cq",
                str(crf),  # NVENC 的质量参数
                "-preset",
                preset,
            ]
        )
    else:
        # 软件 x265 编码
        ffmpeg_cmd.extend(
            [
                "-c:v",
                "libx265",  # 软件x265编码器
                "-crf",
                str(crf),
                "-preset",
                preset,
            ]
        )

    # 如果指定了固定码率，则覆盖质量参数
    if bitrate:
        ffmpeg_cmd.extend(["-b:v", bitrate])

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

    # 新增质量/码率可调参数
    parser.add_argument(
        "--crf",
        type=int,
        default=23,
        help="质量参数（CRF或等效值，数值越大文件越小）",
    )
    parser.add_argument(
        "--preset",
        default="medium",
        choices=[
            "ultrafast",
            "fast",
            "medium",
            "slow",
            "slower",
            "veryslow",
        ],
        help="编码preset",
    )
    parser.add_argument(
        "--bitrate",
        help="目标码率，如2000k，优先于CRF/质量参数",
    )

    args = parser.parse_args()
    if sum(bool(x) for x in (args.intel, args.amd, args.nvidia)) > 1:
        print("错误: 只能指定一个硬件加速选项")
        sys.exit(1)

    convert_to_h265(
        args.input_file,
        use_intel=args.intel,
        use_amd=args.amd,
        use_nvidia=args.nvidia,
        crf=args.crf,
        preset=args.preset,
        bitrate=args.bitrate,
    )
