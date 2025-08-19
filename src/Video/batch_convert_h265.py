#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量扫描指定目录(递归)中的常见视频文件, 使用 ffmpeg 的 AMD AMF 硬件编码器 (hevc_amf)
转码为 H.265 并输出为 MP4。输出文件名规则: 原文件名 + _h265.mp4。

最新规则:
    - 跳过: 文件名包含 _h265 的文件（已转换过的文件）。
    - 直接 remux (不重新编码): 容器不是 mp4 且首视频轨已是 HEVC，封装到 mp4；视频/音频 copy，丢弃字幕附件。
    - 转码: 其它全部 (视频重新编码为 HEVC，音频 copy，丢弃字幕附件)。

转换时处理策略:
    - 仅保留首视频轨 (转码成 HEVC) + 所有音频轨 (copy)。
    - 丢弃字幕 / 附件 / 章节等可能不兼容或可再生提取的信息 (满足“无法兼容的信息直接丢弃”).
    - 输出容器统一 mp4，文件名追加 _h265.mp4。

用法:
    python batch_convert_big_amd_h265.py <目录路径> [--qp 23] [--quality balanced] [--usage high_quality] [--profile main] [--tier main] [--min-qp-i 15] [--max-qp-i 35] [--min-qp-p 18] [--max-qp-p 40] [--vbaq] [--preencode] [--preanalysis] [--caq-strength medium] [--me-half-pel] [--me-quarter-pel] [--max-size 1800] [--two-pass] [--overwrite] [--delete-source] [--extensions ".mkv,.mp4"]

参数说明:
    <目录路径>      根目录
    --qp             质量(AMF CQP qp 0~51)，默认 23 (越大压缩越高画质越差)
    --quality        AMF quality: speed | balanced | quality
    --usage          编码用途: transcoding | ultralowlatency | lowlatency | webcam | high_quality | lowlatency_high_quality
    --profile        编码Profile: main | main10 (默认main)
    --tier           编码Tier: main | high (默认main)
    --min-qp-i       I帧最小QP值 (0-51)
    --max-qp-i       I帧最大QP值 (0-51)
    --min-qp-p       P帧最小QP值 (0-51)
    --max-qp-p       P帧最大QP值 (0-51)
    --vbaq           启用VBAQ(Variance Based Adaptive Quantization)
    --preencode      启用预编码分析
    --preanalysis    启用预分析
    --caq-strength   内容自适应量化强度: low | medium | high
    --me-half-pel    启用半像素运动估计
    --me-quarter-pel 启用四分之一像素运动估计
    --max-size       输出文件最大大小限制(MB)，默认1800MB(约1.8GB)
    --two-pass       启用两遍编码以更精确控制文件大小
    --overwrite      覆盖已存在的 *_h265.mp4
    --delete-source  成功后删除源文件
    --extensions     需要扫描的扩展名(逗号分隔)，默认内置常见视频格式
"""
import argparse
import os
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

# 可调整的默认扫描扩展


def human_size(num: int) -> str:
    size = float(num)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


@dataclass
class EncodeOptions:
    """编码参数配置"""

    qp: int = 23
    quality: str = "balanced"
    usage: str | None = None
    profile: str | None = None
    tier: str | None = None
    min_qp_i: int | None = None
    max_qp_i: int | None = None
    min_qp_p: int | None = None
    max_qp_p: int | None = None
    vbaq: bool = False
    preencode: bool = False
    preanalysis: bool = False
    caq_strength: str | None = None
    me_half_pel: bool = False
    me_quarter_pel: bool = False
    max_size_mb: int | None = None
    two_pass: bool = False


@dataclass
class Task:
    src: str
    dst: str
    size: int
    src_ext: str  # 小写含点
    codec: str | None  # 源首视频编码 (可能为 None)
    action: str  # 'remux' 或 'transcode'


def probe_video_codec(path: str) -> str | None:
    """使用 ffprobe 获取首视频轨 codec_name, 失败返回 None"""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=nw=1:nk=1",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode == 0:
            codec = result.stdout.strip().lower()
            return codec or None
    except Exception:
        return None
    return None


def probe_video_duration(path: str) -> float | None:
    """获取视频时长(秒)"""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode == 0:
            duration_str = result.stdout.strip()
            if duration_str:
                return float(duration_str)
    except Exception:
        return None
    return None


def calculate_target_bitrate(duration_seconds: float, target_size_mb: int) -> int:
    """根据时长和目标文件大小计算目标码率(kbps)
    预留10%空间给音频和开销
    """
    if duration_seconds <= 0:
        return 1000  # 默认码率

    target_size_bits = target_size_mb * 1024 * 1024 * 8  # 转换为bits
    # 预留10%给音频和容器开销
    video_bits = target_size_bits * 0.9
    target_bitrate_bps = video_bits / duration_seconds
    target_bitrate_kbps = int(target_bitrate_bps / 1000)

    # 设置合理的范围限制
    min_bitrate = 500  # 最小500kbps
    max_bitrate = 10000  # 最大10Mbps

    return max(min_bitrate, min(max_bitrate, target_bitrate_kbps))


def is_valid_video(target_path: str, source_path: str | None = None) -> bool:
    """判断目标视频是否可用:
    1) 文件存在 & 可读取首视频轨 codec
    2) 若提供源文件, 再比较时长是否基本一致 (默认允许 <=1.0 秒差)
    """
    if not os.path.exists(target_path):
        return False
    try:
        # 基础可读性(获取首视频轨 codec)
        codec_probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=nw=1:nk=1",
                target_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if codec_probe.returncode != 0 or not codec_probe.stdout.strip():
            return False

        # 若不需要对比时长
        if not source_path:
            return True

        def probe_duration(p: str) -> float | None:
            try:
                r = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=nw=1:nk=1",
                        p,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
                if r.returncode == 0:
                    s = r.stdout.strip()
                    if s:
                        return float(s)
            except Exception:
                return None
            return None

        src_dur = probe_duration(source_path)
        tgt_dur = probe_duration(target_path)
        if src_dur is None or tgt_dur is None:
            # 无法验证时长则视为无效, 以便重新处理
            return False

        DURATION_TOLERANCE = 1.0  # 秒
        if abs(src_dur - tgt_dur) <= DURATION_TOLERANCE:
            return True
        return False
    except Exception:
        return False


def collect_tasks(root: str, exts: Iterable[str], overwrite: bool) -> List[Task]:
    tasks: List[Task] = []
    exts_lower = {e.lower() for e in exts}
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in exts_lower:
                continue
            # 跳过已经转换过的文件（文件名包含 _h265）
            if "_h265" in fn.lower():
                continue
            # 输出目标固定为 _h265.mp4；若已有 _h265.mp4 且无需覆盖则跳过
            full = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            codec = probe_video_codec(full)  # 所有文件都探测
            hevc_like = codec in {"hevc", "h265"}
            # 不再跳过任何文件，所有视频都进行转换
            # 决策 action
            if hevc_like and ext != ".mp4":
                action = "remux"
            else:
                action = "transcode"
            base, _ = os.path.splitext(full)
            dst = base + "_h265.mp4"
            if not overwrite and os.path.exists(dst):
                if is_valid_video(dst, full):
                    print(f"[跳过] 目标已存在且有效(时长匹配): {dst}")
                    continue
                else:
                    print(f"[重建] 目标存在但无效或时长不符，重新处理: {dst}")
            tasks.append(
                Task(
                    src=full,
                    dst=dst,
                    size=size,
                    src_ext=ext,
                    codec=codec,
                    action=action,
                )
            )
    return tasks


def build_ffmpeg_cmd(task: "Task", options: "EncodeOptions") -> List[str]:
    """根据任务类型构建命令:
    remux: 视频/音频 copy -> mp4 (丢字幕)
    transcode: 视频 hevc_amf, 音频 copy -> mp4 (丢字幕)
    """
    base = [
        "ffmpeg",
        "-y",
        "-i",
        task.src,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:a",
        "copy",
        "-sn",
        "-movflags",
        "+faststart",
    ]
    if task.action == "remux":
        base.extend(["-c:v", "copy"])
    else:  # transcode
        # 如果设置了文件大小限制，使用码率控制而不是CQP
        if options.max_size_mb:
            duration = probe_video_duration(task.src)
            if duration:
                target_bitrate = calculate_target_bitrate(duration, options.max_size_mb)
                print(
                    f"  目标码率: {target_bitrate}kbps (时长: {duration:.1f}s, 目标大小: {options.max_size_mb}MB)"
                )

                if options.two_pass:
                    # 两遍编码模式 - 这里只返回第一遍命令，第二遍需要单独处理
                    base.extend(
                        [
                            "-c:v",
                            "hevc_amf",
                            "-rc",
                            "vbr_peak",
                            "-b:v",
                            f"{target_bitrate}k",
                            "-maxrate",
                            f"{int(target_bitrate * 1.2)}k",
                            "-bufsize",
                            f"{int(target_bitrate * 2)}k",
                        ]
                    )
                else:
                    # 单遍VBR编码
                    base.extend(
                        [
                            "-c:v",
                            "hevc_amf",
                            "-rc",
                            "vbr_peak",
                            "-b:v",
                            f"{target_bitrate}k",
                            "-maxrate",
                            f"{int(target_bitrate * 1.1)}k",
                            "-bufsize",
                            f"{int(target_bitrate * 1.5)}k",
                            "-quality",
                            options.quality,
                        ]
                    )
            else:
                print("  警告: 无法获取视频时长，使用CQP模式")
                base.extend(
                    [
                        "-c:v",
                        "hevc_amf",
                        "-rc",
                        "cqp",
                        "-qp",
                        str(options.qp),
                        "-quality",
                        options.quality,
                    ]
                )
        else:
            # 原有的CQP模式
            base.extend(
                [
                    "-c:v",
                    "hevc_amf",
                    "-rc",
                    "cqp",
                    "-qp",
                    str(options.qp),
                    "-quality",
                    options.quality,
                ]
            )

        # 添加其他编码参数
        if options.usage:
            base.extend(["-usage", options.usage])
        if options.profile:
            base.extend(["-profile", options.profile])
        if options.tier:
            base.extend(["-profile_tier", options.tier])
        if options.min_qp_i is not None:
            base.extend(["-min_qp_i", str(options.min_qp_i)])
        if options.max_qp_i is not None:
            base.extend(["-max_qp_i", str(options.max_qp_i)])
        if options.min_qp_p is not None:
            base.extend(["-min_qp_p", str(options.min_qp_p)])
        if options.max_qp_p is not None:
            base.extend(["-max_qp_p", str(options.max_qp_p)])
        if options.vbaq:
            base.extend(["-vbaq", "true"])
        if options.preencode:
            base.extend(["-preencode", "true"])
        if options.preanalysis:
            base.extend(["-preanalysis", "true"])
        if options.caq_strength:
            base.extend(["-pa_caq_strength", options.caq_strength])
        if options.me_half_pel:
            base.extend(["-me_half_pel", "true"])
        if options.me_quarter_pel:
            base.extend(["-me_quarter_pel", "true"])

    base.append(task.dst)
    return base


def run_cmd(cmd: List[str]) -> int:
    # 动态刷新同一行显示包含 frame / speed 的进度（覆盖上一行）
    # Windows 默认控制台编码可能不是 UTF-8，强制使用 utf-8 并容错
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,  # 等价于 universal_newlines
        encoding="utf-8",
        errors="replace",  # 避免因非法字节崩溃
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
        "--usage",
        choices=[
            "transcoding",
            "ultralowlatency",
            "lowlatency",
            "webcam",
            "high_quality",
            "lowlatency_high_quality",
        ],
        help="编码用途，默认无指定",
    )
    parser.add_argument(
        "--profile",
        choices=["main", "main10"],
        help="编码Profile，默认无指定",
    )
    parser.add_argument(
        "--tier",
        choices=["main", "high"],
        help="编码Tier，默认无指定",
    )
    parser.add_argument(
        "--min-qp-i",
        type=int,
        help="I帧最小QP值(0-51)",
    )
    parser.add_argument(
        "--max-qp-i",
        type=int,
        help="I帧最大QP值(0-51)",
    )
    parser.add_argument(
        "--min-qp-p",
        type=int,
        help="P帧最小QP值(0-51)",
    )
    parser.add_argument(
        "--max-qp-p",
        type=int,
        help="P帧最大QP值(0-51)",
    )
    parser.add_argument(
        "--vbaq",
        action="store_true",
        help="启用VBAQ(Variance Based Adaptive Quantization)",
    )
    parser.add_argument(
        "--preencode",
        action="store_true",
        help="启用预编码分析",
    )
    parser.add_argument(
        "--preanalysis",
        action="store_true",
        help="启用预分析",
    )
    parser.add_argument(
        "--caq-strength",
        choices=["low", "medium", "high"],
        help="内容自适应量化强度",
    )
    parser.add_argument(
        "--me-half-pel",
        action="store_true",
        help="启用半像素运动估计",
    )
    parser.add_argument(
        "--me-quarter-pel",
        action="store_true",
        help="启用四分之一像素运动估计",
    )
    parser.add_argument(
        "--max-size",
        type=int,
        default=1800,
        help="输出文件最大大小限制(MB)，默认1800MB(约1.8GB)，设为0禁用",
    )
    parser.add_argument(
        "--two-pass",
        action="store_true",
        help="启用两遍编码以更精确控制文件大小(仅在设置max-size时有效)",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="覆盖已存在的 *_h265 输出文件"
    )
    parser.add_argument(
        "--delete-source", action="store_true", help="转码成功后删除源文件"
    )
    parser.add_argument(
        "--extensions",
        help="自定义扩展名列表, 逗号分隔，如 .mp4,.mkv (默认内置常见格式)",
    )
    args = parser.parse_args()

    if args.qp < 0 or args.qp > 51:
        print("qp 应在 0~51 之间")
        return 1

    # 创建编码选项对象
    options = EncodeOptions(
        qp=args.qp,
        quality=args.quality,
        usage=args.usage,
        profile=args.profile,
        tier=args.tier,
        min_qp_i=getattr(args, "min_qp_i", None),
        max_qp_i=getattr(args, "max_qp_i", None),
        min_qp_p=getattr(args, "min_qp_p", None),
        max_qp_p=getattr(args, "max_qp_p", None),
        vbaq=args.vbaq,
        preencode=args.preencode,
        preanalysis=args.preanalysis,
        caq_strength=getattr(args, "caq_strength", None),
        me_half_pel=getattr(args, "me_half_pel", False),
        me_quarter_pel=getattr(args, "me_quarter_pel", False),
        max_size_mb=args.max_size if args.max_size > 0 else None,
        two_pass=args.two_pass,
    )

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
    print(f"使用扩展名: {', '.join(exts)}")
    if options.max_size_mb:
        print(
            f"文件大小限制: {options.max_size_mb}MB (约{options.max_size_mb/1024:.1f}GB)"
        )
        print("编码模式: VBR码率控制")
    else:
        print(f"编码模式: CQP质量控制 (QP={options.qp})")
    print("转换规则: 跳过已转换(_h265) | 非mp4+HEVC remux | 其它 transcode -> mp4+h265")

    tasks = collect_tasks(args.root, exts, args.overwrite)
    if not tasks:
        print("未找到需要转码的文件。")
        return 0

    total_size = sum(t.size for t in tasks)
    print(f"共发现 {len(tasks)} 个待转码文件 (待处理数据量 {human_size(total_size)})")

    success = 0
    for idx, task in enumerate(tasks, 1):
        print("=" * 80)
        print(f"[{idx}/{len(tasks)}] 转码: {task.src}")
        print(f"大小: {human_size(task.size)}")
        cmd = build_ffmpeg_cmd(task, options)
        ret = run_cmd(cmd)
        if ret == 0 and os.path.exists(task.dst):
            output_size = os.path.getsize(task.dst)
            success += 1
            ratio = output_size / task.size
            print(f"完成 -> 压缩比: {ratio:.2%}")

            # 检查文件大小是否超出限制
            if options.max_size_mb:
                max_size_bytes = options.max_size_mb * 1024 * 1024
                if output_size > max_size_bytes:
                    print(
                        f"警告: 输出文件 {human_size(output_size)} 超过限制 {options.max_size_mb}MB"
                    )
                    # 可以选择重新编码或调整参数
                else:
                    print(f"文件大小: {human_size(output_size)} (在限制内)")

            if args.delete_source:
                try:
                    os.remove(task.src)
                    print(f"已删除源文件: {task.src}")
                except Exception as e:
                    print(f"删除源文件失败: {e}")
        else:
            print(f"失败 (exit={ret})")
    print("=" * 80)
    print(f"完成: {success}/{len(tasks)} 成功")
    return 0 if success == len(tasks) else 2


if __name__ == "__main__":
    sys.exit(main())
