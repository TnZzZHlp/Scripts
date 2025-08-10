#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量扫描指定目录(递归)中大于阈值(默认2GB)的常见视频文件, 使用 ffmpeg 的 AMD AMF 硬件编码器 (hevc_amf)
转码为 H.265，输出文件名规则: 原文件名 + _h265 + 原扩展名。

用法:
    python batch_convert_big_amd_h265.py <目录路径> [--min-size 2G] [--qp 23] [--quality balanced] [--overwrite] [--extensions ".mkv,.mp4"]

参数说明:
    <目录路径>      需要扫描的根目录
    --min-size       最小文件大小(支持 K/M/G 后缀)，默认 2G
    --qp             质量(整数，AMF CQP 的 qp 值，范围通常 0~51)，默认 23 (值越大体积越小画质越差)
    --quality        AMF 的 quality 级别: speed | balanced | quality，默认 balanced
    --overwrite      如果输出文件已存在则覆盖；默认跳过
    --extensions     逗号分隔的扩展名列表(不区分大小写)，默认内置常见视频格式

注意:
    1. 需要本机 ffmpeg 已编译支持 hevc_amf。
    2. 将直接复制音频与字幕流 (copy)。
    3. 已经带有 _h265 后缀的文件会被自动跳过。
"""
import argparse
import os
import re
import sys
import subprocess
from dataclasses import dataclass
from typing import Iterable, List

DEFAULT_EXTS = [
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".flv",
    ".ts",
    ".m4v",
    ".wmv",
]

SIZE_PATTERN = re.compile(r"^(\d+)([KMG]?)$", re.IGNORECASE)


def parse_size(size_text: str) -> int:
    """将 '2G' / '1500M' / '500000K' / '123456' 转换为字节数"""
    m = SIZE_PATTERN.match(size_text.strip())
    if not m:
        raise ValueError(f"无法解析的大小: {size_text}")
    value = int(m.group(1))
    unit = m.group(2).upper()
    if unit == "K":
        value *= 1024
    elif unit == "M":
        value *= 1024**2
    elif unit == "G":
        value *= 1024**3
    return value


def human_size(num: int) -> str:
    size = float(num)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


@dataclass
class Task:
    src: str
    dst: str
    size: int


def collect_tasks(
    root: str, min_size: int, exts: Iterable[str], overwrite: bool
) -> List[Task]:
    tasks: List[Task] = []
    exts_lower = {e.lower() for e in exts}
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in exts_lower:
                continue
            if fn.lower().endswith("_h265" + ext):  # 已处理
                continue
            full = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            if size < min_size:
                continue
            base, _ = os.path.splitext(full)
            dst = base + "_h265" + ext
            if not overwrite and os.path.exists(dst):
                print(f"[跳过] 目标已存在: {dst}")
                continue
            tasks.append(Task(src=full, dst=dst, size=size))
    return tasks


def build_ffmpeg_cmd(task: Task, qp: int, quality: str) -> List[str]:
    # AMD AMF hevc 参数: 使用 CQP 模式 -rc cqp -qp <qp> -quality <quality>
    return [
        "ffmpeg",
        "-y",
        "-i",
        task.src,
        "-c:v",
        "hevc_amf",
        "-rc",
        "cqp",
        "-qp",
        str(qp),
        "-quality",
        quality,
        "-c:a",
        "copy",
        "-c:s",
        "copy",
        task.dst,
    ]


def run_cmd(cmd: List[str]) -> int:
    # 动态刷新同一行显示包含 frame / speed 的进度（覆盖上一行）
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True
    )
    assert process.stdout is not None
    prev_len = 0
    for line in process.stdout:
        if any(key in line for key in ("frame=", "speed=")):
            text = line.rstrip()
            pad = " " * max(0, prev_len - len(text))  # 清除残余字符
            print("\r" + text + pad, end="", flush=True)
            prev_len = len(text)
    print()  # 结束时换行
    return process.wait()


def main():
    parser = argparse.ArgumentParser(
        description="批量将>指定大小的视频转码为H.265(AMD)"
    )
    parser.add_argument("root", help="待扫描根目录")
    parser.add_argument(
        "--min-size", default="2G", help="最小文件大小阈值，支持K/M/G，默认2G"
    )
    parser.add_argument(
        "--qp",
        type=int,
        default=23,
        help="AMF CQP qp值(0-51, 越大压缩率越高画质越低)，默认23",
    )
    parser.add_argument(
        "--quality",
        choices=["speed", "balanced", "quality"],
        default="balanced",
        help="AMF quality 级别，默认 balanced",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="覆盖已存在的 *_h265 输出文件"
    )
    parser.add_argument(
        "--extensions",
        help="自定义扩展名列表, 逗号分隔，如 .mp4,.mkv (默认内置常见格式)",
    )
    args = parser.parse_args()

    try:
        min_size = parse_size(args.min_size)
    except ValueError as e:
        print(e)
        return 1

    if args.qp < 0 or args.qp > 51:
        print("qp 应在 0~51 之间")
        return 1

    if args.extensions:
        exts = [
            e.strip().lower() if e.strip().startswith(".") else "." + e.strip().lower()
            for e in args.extensions.split(",")
            if e.strip()
        ]
    else:
        exts = DEFAULT_EXTS

    if not os.path.isdir(args.root):
        print(f"目录不存在: {args.root}")
        return 1

    print(f"扫描目录: {args.root}")
    print(f"最小大小: {human_size(min_size)}")
    print(f"使用扩展名: {', '.join(exts)}")

    tasks = collect_tasks(args.root, min_size, exts, args.overwrite)
    if not tasks:
        print("未找到需要转码的文件。")
        return 0

    total_size = sum(t.size for t in tasks)
    print(f"共发现 {len(tasks)} 个待转码文件，总体积 {human_size(total_size)}")

    success = 0
    for idx, task in enumerate(tasks, 1):
        print("=" * 80)
        print(f"[{idx}/{len(tasks)}] 转码: {task.src}")
        print(f"大小: {human_size(task.size)}")
        print(f"输出: {task.dst}")
        cmd = build_ffmpeg_cmd(task, args.qp, args.quality)
        # 打印命令(可注释)
        print("命令:", " ".join(cmd))
        ret = run_cmd(cmd)
        if ret == 0 and os.path.exists(task.dst):
            success += 1
            ratio = os.path.getsize(task.dst) / task.size
            print(f"完成 -> 压缩比: {ratio:.2%}")
        else:
            print(f"失败 (exit={ret})")
    print("=" * 80)
    print(f"完成: {success}/{len(tasks)} 成功")
    return 0 if success == len(tasks) else 2


if __name__ == "__main__":
    sys.exit(main())
