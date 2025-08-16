#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检测指定目录下相同的视频文件

功能特性:
    1. 递归扫描指定目录下的视频文件
    2. 支持多种检测方式:
       - 文件大小比较 (快速初筛)
       - MD5 哈希值比较 (准确但较慢)
       - 文件名相似度比较
       - 视频时长比较 (±3秒内视为相同)
    3. 支持多种视频格式
    4. 提供详细的重复文件报告
    5. 可选择删除重复文件 (保留文件大小最大的文件)

用法:
    python detect_duplicate_videos.py <目录路径> [选项]

参数说明:
    <目录路径>          要扫描的根目录
    --method            检测方法: size | hash | name | duration | frames | all (默认: hash)
    --extensions        支持的视频格式 (默认: .mp4,.mkv,.avi,.mov,.flv,.wmv,.m4v,.ts)
    --similarity        文件名相似度阈值 (0-1, 仅在name方法时使用, 默认: 0.8)
    --duration-tolerance 视频时长容差 (秒, 仅在duration/frames方法时使用, 默认: 3)
    --frame-similarity  画面相似度阈值 (0-1, 仅在frames方法时使用, 默认: 0.8)
    --max-frames        提取的视频帧数 (仅在frames方法时使用, 默认: 30)
    --delete            删除重复文件 (保留文件大小最大的文件)
    --dry-run           仅显示会删除的文件，不实际删除
    --output            输出报告到文件
    --verbose           显示详细信息

示例:
    python detect_duplicate_videos.py "D:/Videos" --method duration --duration-tolerance 5
    python detect_duplicate_videos.py "D:/Videos" --method frames --frame-similarity 0.9 --max-frames 50
    python detect_duplicate_videos.py "D:/Videos" --method all --delete --dry-run
    python detect_duplicate_videos.py "D:/Videos" --output "duplicate_report.txt"
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import cv2
import numpy as np
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import time


@dataclass
class VideoFile:
    """视频文件信息"""

    path: str
    size: int
    name: str
    hash_md5: str = ""
    duration: float = -1.0  # 视频时长（秒）
    frame_hash: str = ""  # 前30帧的哈希值


class DuplicateVideoDetector:
    """重复视频文件检测器"""

    DEFAULT_VIDEO_EXTENSIONS = {
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".flv",
        ".wmv",
        ".m4v",
        ".ts",
        ".webm",
        ".mpg",
        ".mpeg",
        ".3gp",
        ".f4v",
        ".asf",
        ".rm",
        ".rmvb",
    }

    def __init__(
        self,
        root_dir: str,
        extensions: Optional[Set[str]] = None,
        verbose: bool = False,
    ):
        """
        初始化检测器

        Args:
            root_dir: 根目录
            extensions: 支持的视频扩展名
            verbose: 是否显示详细信息
        """
        self.root_dir = Path(root_dir)
        self.extensions = extensions or self.DEFAULT_VIDEO_EXTENSIONS
        self.verbose = verbose
        self.video_files: List[VideoFile] = []

    def scan_video_files(self) -> None:
        """扫描目录下的所有视频文件"""
        if self.verbose:
            print(f"正在扫描目录: {self.root_dir}")

        count = 0
        for file_path in self.root_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in self.extensions:
                try:
                    file_size = file_path.stat().st_size
                    video_file = VideoFile(
                        path=str(file_path), size=file_size, name=file_path.name
                    )
                    self.video_files.append(video_file)
                    count += 1

                    if self.verbose and count % 100 == 0:
                        print(f"已扫描 {count} 个视频文件...")

                except (OSError, PermissionError) as e:
                    if self.verbose:
                        print(f"无法访问文件 {file_path}: {e}")

        if self.verbose:
            print(f"扫描完成，共找到 {len(self.video_files)} 个视频文件")

    def calculate_file_hash(self, file_path: str, chunk_size: int = 8192) -> str:
        """计算文件的MD5哈希值"""
        hasher = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except (OSError, PermissionError):
            return ""

    def get_video_duration(self, file_path: str) -> float:
        """获取视频时长（秒）"""
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                file_path,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="ignore",  # 忽略编码错误
            )

            if result.returncode == 0 and result.stdout:
                try:
                    data = json.loads(result.stdout)
                    if "format" in data and "duration" in data["format"]:
                        return float(data["format"]["duration"])
                except (json.JSONDecodeError, ValueError, KeyError):
                    if self.verbose:
                        print(f"解析JSON失败 {file_path}: 输出内容无效")
            elif self.verbose:
                error_msg = result.stderr if result.stderr else "未知错误"
                print(f"ffprobe执行失败 {file_path}: {error_msg}")

        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            FileNotFoundError,
        ) as e:
            if self.verbose:
                print(f"无法获取视频时长 {file_path}: {e}")

        return -1.0

    def extract_video_frames(
        self, file_path: str, max_frames: int = 30
    ) -> List[np.ndarray]:
        """提取视频的前N帧"""
        frames = []
        try:
            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                if self.verbose:
                    print(f"无法打开视频文件: {file_path}")
                return frames

            frame_count = 0
            while frame_count < max_frames:
                ret, frame = cap.read()
                if not ret:
                    break

                # 将帧转换为灰度图像并调整大小以提高比较效率
                gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                resized_frame = cv2.resize(gray_frame, (64, 64))
                frames.append(resized_frame)
                frame_count += 1

            cap.release()

        except Exception as e:
            if self.verbose:
                print(f"提取视频帧失败 {file_path}: {e}")

        return frames

    def calculate_frame_hash(self, frames: List[np.ndarray]) -> str:
        """计算帧序列的哈希值"""
        if not frames:
            return ""

        try:
            # 将所有帧连接成一个大的数组
            combined_frames = np.concatenate([frame.flatten() for frame in frames])
            # 计算哈希值
            hasher = hashlib.md5()
            hasher.update(combined_frames.tobytes())
            return hasher.hexdigest()
        except Exception:
            return ""

    def calculate_frame_similarity(
        self, frames1: List[np.ndarray], frames2: List[np.ndarray]
    ) -> float:
        """计算两个帧序列的相似度"""
        if not frames1 or not frames2:
            return 0.0

        # 确保两个序列长度相同
        min_len = min(len(frames1), len(frames2))
        frames1 = frames1[:min_len]
        frames2 = frames2[:min_len]

        similarities = []
        for f1, f2 in zip(frames1, frames2):
            try:
                # 使用结构相似性指数 (SSIM)
                # 由于cv2没有直接的SSIM，我们使用简单的相关系数
                correlation = cv2.matchTemplate(f1, f2, cv2.TM_CCOEFF_NORMED)[0][0]
                similarities.append(max(0, correlation))  # 确保非负
            except Exception:
                similarities.append(0.0)

        return float(np.mean(similarities)) if similarities else 0.0

    def detect_by_size(self) -> Dict[int, List[VideoFile]]:
        """基于文件大小检测重复文件"""
        if self.verbose:
            print("正在基于文件大小检测重复文件...")

        size_groups = defaultdict(list)
        for video_file in self.video_files:
            size_groups[video_file.size].append(video_file)

        # 只返回有重复的组
        duplicates = {
            size: files for size, files in size_groups.items() if len(files) > 1
        }

        if self.verbose:
            print(f"找到 {len(duplicates)} 组大小相同的文件")

        return duplicates

    def detect_by_hash(self) -> Dict[str, List[VideoFile]]:
        """基于文件哈希值检测重复文件"""
        if self.verbose:
            print("正在计算文件哈希值...")

        hash_groups = defaultdict(list)
        total_files = len(self.video_files)

        for i, video_file in enumerate(self.video_files):
            if self.verbose and (i + 1) % 10 == 0:
                print(
                    f"进度: {i + 1}/{total_files} ({(i + 1) / total_files * 100:.1f}%)"
                )

            video_file.hash_md5 = self.calculate_file_hash(video_file.path)
            if video_file.hash_md5:
                hash_groups[video_file.hash_md5].append(video_file)

        # 只返回有重复的组
        duplicates = {
            hash_val: files for hash_val, files in hash_groups.items() if len(files) > 1
        }

        if self.verbose:
            print(f"找到 {len(duplicates)} 组哈希值相同的文件")

        return duplicates

    def detect_by_name_similarity(
        self, similarity_threshold: float = 0.8
    ) -> Dict[str, List[VideoFile]]:
        """基于文件名相似度检测可能重复的文件"""
        if self.verbose:
            print(f"正在基于文件名相似度检测 (阈值: {similarity_threshold})...")

        similar_groups = defaultdict(list)
        processed = set()

        for i, file1 in enumerate(self.video_files):
            if i in processed:
                continue

            group_key = f"group_{i}"
            similar_groups[group_key].append(file1)
            processed.add(i)

            for j, file2 in enumerate(self.video_files[i + 1 :], i + 1):
                if j in processed:
                    continue

                # 计算文件名相似度
                similarity = SequenceMatcher(
                    None, file1.name.lower(), file2.name.lower()
                ).ratio()
                if similarity >= similarity_threshold:
                    similar_groups[group_key].append(file2)
                    processed.add(j)

        # 只返回有重复的组
        duplicates = {
            key: files for key, files in similar_groups.items() if len(files) > 1
        }

        if self.verbose:
            print(f"找到 {len(duplicates)} 组名称相似的文件")

        return duplicates

    def detect_by_duration(
        self, duration_tolerance: float = 3.0
    ) -> Dict[str, List[VideoFile]]:
        """基于视频时长检测重复文件（允许指定容差）"""
        if self.verbose:
            print(f"正在获取视频时长信息 (容差: ±{duration_tolerance}秒)...")

        # 首先获取所有视频的时长
        total_files = len(self.video_files)
        valid_files = []

        for i, video_file in enumerate(self.video_files):
            if self.verbose and (i + 1) % 10 == 0:
                print(
                    f"进度: {i + 1}/{total_files} ({(i + 1) / total_files * 100:.1f}%)"
                )

            duration = self.get_video_duration(video_file.path)
            if duration > 0:
                video_file.duration = duration
                valid_files.append(video_file)
            elif self.verbose:
                print(f"跳过无法获取时长的文件: {video_file.path}")

        if self.verbose:
            print(f"成功获取 {len(valid_files)} 个文件的时长信息")

        # 根据时长分组（考虑容差）
        duration_groups = defaultdict(list)
        processed = set()

        for i, file1 in enumerate(valid_files):
            if i in processed:
                continue

            # 为这个时长创建一个组
            group_key = f"duration_{file1.duration:.1f}"
            duration_groups[group_key].append(file1)
            processed.add(i)

            # 寻找时长相近的其他文件
            for j, file2 in enumerate(valid_files[i + 1 :], i + 1):
                if j in processed:
                    continue

                # 检查时长差异是否在容差范围内
                duration_diff = abs(file1.duration - file2.duration)
                if duration_diff <= duration_tolerance:
                    duration_groups[group_key].append(file2)
                    processed.add(j)

        # 只返回有重复的组
        duplicates = {
            key: files for key, files in duration_groups.items() if len(files) > 1
        }

        if self.verbose:
            print(f"找到 {len(duplicates)} 组时长相近的文件")

        return duplicates

    def detect_by_duration_and_frames(
        self,
        duration_tolerance: float = 3.0,
        frame_similarity_threshold: float = 0.8,
        max_frames: int = 30,
    ) -> Dict[str, List[VideoFile]]:
        """基于视频时长和前N帧画面检测重复文件"""
        if self.verbose:
            print(
                f"正在进行时长+画面检测 (时长容差: ±{duration_tolerance}秒, 画面相似度阈值: {frame_similarity_threshold}, 提取帧数: {max_frames})..."
            )

        # 首先基于时长进行初步筛选
        duration_candidates = self.detect_by_duration(duration_tolerance)

        if not duration_candidates:
            if self.verbose:
                print("没有时长相近的文件，跳过画面比对")
            return {}

        # 对时长相近的文件进行画面比对
        frame_duplicates = defaultdict(list)
        processed_groups = 0
        total_groups = len(duration_candidates)

        for group_key, files in duration_candidates.items():
            processed_groups += 1
            if self.verbose:
                print(
                    f"正在处理第 {processed_groups}/{total_groups} 组时长相近的文件..."
                )

            if len(files) < 2:
                continue

            # 提取每个文件的前N帧
            file_frames = {}
            for video_file in files:
                if self.verbose:
                    print(f"  提取帧: {video_file.name}")
                frames = self.extract_video_frames(video_file.path, max_frames)
                if frames:
                    file_frames[video_file.path] = (video_file, frames)

            # 比较画面相似度
            processed_files = set()
            similar_group_count = 0

            for path1, (file1, frames1) in file_frames.items():
                if path1 in processed_files:
                    continue

                similar_files = [file1]
                processed_files.add(path1)

                for path2, (file2, frames2) in file_frames.items():
                    if path2 in processed_files:
                        continue

                    similarity = self.calculate_frame_similarity(frames1, frames2)
                    if self.verbose:
                        print(
                            f"    相似度 {file1.name} vs {file2.name}: {similarity:.3f}"
                        )

                    if similarity >= frame_similarity_threshold:
                        similar_files.append(file2)
                        processed_files.add(path2)

                if len(similar_files) > 1:
                    frame_group_key = f"{group_key}_frames_{similar_group_count}"
                    frame_duplicates[frame_group_key] = similar_files
                    similar_group_count += 1

        if self.verbose:
            print(f"找到 {len(frame_duplicates)} 组画面相似的文件")

        return frame_duplicates

    def format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        size = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def format_duration(self, seconds: float) -> str:
        """格式化视频时长"""
        if seconds < 0:
            return "未知"

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

    def print_duplicates_report(self, duplicates: Dict, method_name: str) -> None:
        """打印重复文件报告"""
        if not duplicates:
            print(f"\n使用 {method_name} 方法未发现重复文件")
            return

        print(f"\n=== {method_name} 方法检测结果 ===")
        total_duplicates = 0
        total_wasted_space = 0

        for group_key, files in duplicates.items():
            if len(files) <= 1:
                continue

            total_duplicates += len(files) - 1
            file_size = files[0].size
            wasted_space = file_size * (len(files) - 1)
            total_wasted_space += wasted_space

            print(
                f"\n重复组 (共 {len(files)} 个文件, 浪费空间: {self.format_file_size(wasted_space)}):"
            )

            # 按文件大小排序，最大的在前面
            sorted_files = sorted(files, key=lambda x: x.size, reverse=True)

            for i, file in enumerate(sorted_files):
                status = "[保留]" if i == 0 else "[重复]"
                duration_info = (
                    f" ({self.format_duration(file.duration)})"
                    if file.duration > 0
                    else ""
                )
                print(
                    f"  {status} {self.format_file_size(file.size)}{duration_info} - {file.path}"
                )

        print(f"\n总结:")
        print(f"  重复文件数量: {total_duplicates}")
        print(f"  浪费的存储空间: {self.format_file_size(total_wasted_space)}")

    def delete_duplicates(
        self, duplicates: Dict, dry_run: bool = True
    ) -> Tuple[int, int]:
        """删除重复文件，保留文件大小最大的文件"""
        deleted_count = 0
        failed_count = 0

        for group_key, files in duplicates.items():
            if len(files) <= 1:
                continue

            # 按文件大小排序，保留最大的
            sorted_files = sorted(files, key=lambda x: x.size, reverse=True)
            files_to_delete = sorted_files[1:]  # 除了第一个（最大文件）之外的所有文件

            for file in files_to_delete:
                try:
                    if dry_run:
                        print(f"[模拟] 将删除: {file.path}")
                    else:
                        os.remove(file.path)
                        print(f"[已删除] {file.path}")
                    deleted_count += 1
                except OSError as e:
                    print(f"[删除失败] {file.path}: {e}")
                    failed_count += 1

        return deleted_count, failed_count


def main():
    parser = argparse.ArgumentParser(
        description="检测指定目录下相同的视频文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python detect_duplicate_videos.py "D:/Videos" --method all --delete --dry-run
  python detect_duplicate_videos.py "D:/Videos" --output "duplicate_report.txt"
        """,
    )

    parser.add_argument("directory", help="要扫描的目录路径")
    parser.add_argument(
        "--method",
        choices=["size", "hash", "name", "duration", "frames", "all"],
        default="frames",
        help="检测方法 (默认: frames)",
    )
    parser.add_argument(
        "--extensions", help="支持的视频格式，用逗号分隔 (默认: 常见视频格式)"
    )
    parser.add_argument(
        "--similarity",
        type=float,
        default=0.8,
        help="文件名相似度阈值 (0-1, 默认: 0.8)",
    )
    parser.add_argument(
        "--duration-tolerance",
        type=float,
        default=3,
        help="视频时长容差(秒) (默认: 3)",
    )
    parser.add_argument(
        "--frame-similarity",
        type=float,
        default=0.8,
        help="画面相似度阈值 (0-1, 默认: 0.8)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=30,
        help="提取的视频帧数 (默认: 30)",
    )
    parser.add_argument(
        "--delete", action="store_true", help="删除重复文件 (保留文件大小最大的文件)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="仅显示会删除的文件，不实际删除"
    )
    parser.add_argument("--output", help="输出报告到指定文件")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细信息")

    args = parser.parse_args()

    # 验证目录
    if not os.path.isdir(args.directory):
        print(f"错误: 目录不存在 - {args.directory}")
        sys.exit(1)

    # 解析扩展名
    extensions: Optional[Set[str]] = None
    if args.extensions:
        extensions = {ext.strip().lower() for ext in args.extensions.split(",")}
        if not all(ext.startswith(".") for ext in extensions):
            extensions = {
                f".{ext}" if not ext.startswith(".") else ext for ext in extensions
            }

    # 创建检测器
    detector = DuplicateVideoDetector(
        root_dir=args.directory,
        extensions=extensions,
        verbose=args.verbose,
    )

    # 扫描文件
    detector.scan_video_files()

    if not detector.video_files:
        print("未找到符合条件的视频文件")
        sys.exit(0)

    # 执行检测
    all_duplicates = {}

    if args.method in ["size", "all"]:
        duplicates = detector.detect_by_size()
        all_duplicates["文件大小"] = duplicates
        detector.print_duplicates_report(duplicates, "文件大小")

    if args.method in ["hash", "all"]:
        duplicates = detector.detect_by_hash()
        all_duplicates["哈希值"] = duplicates
        detector.print_duplicates_report(duplicates, "哈希值")

    if args.method in ["name", "all"]:
        duplicates = detector.detect_by_name_similarity(args.similarity)
        all_duplicates["文件名相似度"] = duplicates
        detector.print_duplicates_report(duplicates, "文件名相似度")

    if args.method in ["duration", "all"]:
        duplicates = detector.detect_by_duration(args.duration_tolerance)
        all_duplicates["视频时长"] = duplicates
        detector.print_duplicates_report(duplicates, "视频时长")

    if args.method in ["frames", "all"]:
        duplicates = detector.detect_by_duration_and_frames(
            args.duration_tolerance, args.frame_similarity, args.max_frames
        )
        all_duplicates["时长+画面"] = duplicates
        detector.print_duplicates_report(duplicates, "时长+画面")

    # 删除重复文件 (hash和duration方法都比较可靠)
    if args.delete:
        target_duplicates = None
        method_name = ""

        if "哈希值" in all_duplicates and all_duplicates["哈希值"]:
            target_duplicates = all_duplicates["哈希值"]
            method_name = "哈希值"
        elif "时长+画面" in all_duplicates and all_duplicates["时长+画面"]:
            target_duplicates = all_duplicates["时长+画面"]
            method_name = "时长+画面"
        elif "视频时长" in all_duplicates and all_duplicates["视频时长"]:
            target_duplicates = all_duplicates["视频时长"]
            method_name = "视频时长"

        if target_duplicates:
            print(
                f"\n使用{method_name}方法{'模拟' if args.dry_run else '开始'}删除重复文件..."
            )
            deleted, failed = detector.delete_duplicates(
                target_duplicates, args.dry_run
            )
            print(
                f"\n删除完成: {deleted} 个文件{'将被' if args.dry_run else '已'}删除, {failed} 个失败"
            )
        else:
            print("\n没有足够可靠的重复文件检测结果可用于删除操作")
            print(
                "建议使用 --method hash, --method frames 或 --method duration 进行更准确的检测"
            )


if __name__ == "__main__":
    main()
