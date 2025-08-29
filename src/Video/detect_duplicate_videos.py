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
    --extract-seconds   提取视频前后多少秒的帧进行比较 (仅在frames方法时使用, 默认: 5.0)
    --frame-position    选择提取哪部分的帧: start(开头)/end(结尾)/both(前后都比较) (默认: both)
    --delete            删除重复文件 (保留文件大小最大的文件)
    --dry-run           仅显示会删除的文件，不实际删除
    --output            输出报告到文件
    --verbose           显示详细信息

示例:
    python detect_duplicate_videos.py "D:/Videos" --method duration --duration-tolerance 5
    python detect_duplicate_videos.py "D:/Videos" --method frames --frame-similarity 0.9 --extract-seconds 5
    python detect_duplicate_videos.py "D:/Videos" --method frames --frame-position middle --extract-seconds 5
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
from datetime import datetime


class ProgressDisplay:
    """进度显示工具类"""

    def __init__(self, total: int, description: str = "", verbose: bool = True):
        self.total = total
        self.current = 0
        self.description = description
        self.verbose = verbose
        self.start_time = time.time()
        self.last_update_time = 0
        self.update_interval = 1.0  # 每秒更新一次

    def update(self, increment: int = 1, item_name: str = ""):
        """更新进度"""
        self.current += increment
        current_time = time.time()

        # 控制更新频率，避免输出过于频繁
        if (
            current_time - self.last_update_time
        ) < self.update_interval and self.current < self.total:
            return

        self.last_update_time = current_time

        if self.total > 0:
            percentage = (self.current / self.total) * 100
            elapsed_time = current_time - self.start_time

            # 计算预估剩余时间
            if self.current > 0:
                avg_time_per_item = elapsed_time / self.current
                remaining_items = self.total - self.current
                eta = remaining_items * avg_time_per_item
                eta_str = self._format_time(eta)
            else:
                eta_str = "未知"

            # 格式化已用时间
            elapsed_str = self._format_time(elapsed_time)

            # 创建进度条
            bar_length = 30
            filled_length = int(bar_length * self.current // self.total)
            bar = "█" * filled_length + "░" * (bar_length - filled_length)

            progress_text = f"\r{self.description} [{bar}] {self.current}/{self.total} ({percentage:.1f}%) | 已用时: {elapsed_str} | 预计剩余: {eta_str}"

            if item_name:
                # 截断过长的文件名
                if len(item_name) > 50:
                    item_name = item_name[:47] + "..."
                progress_text += f" | 当前: {item_name}"

            print(progress_text, end="", flush=True)

            if self.current >= self.total:
                print()  # 完成时换行

    def _format_time(self, seconds: float) -> str:
        """格式化时间显示"""
        if seconds < 60:
            return f"{seconds:.1f}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}分{secs}秒"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}小时{minutes}分钟"

    def finish(self, success_message: str = ""):
        """完成进度显示"""
        if self.verbose:
            if self.current < self.total:
                self.current = self.total
                self.update(0)

            total_time = time.time() - self.start_time
            if success_message:
                print(f"{success_message} (总用时: {self._format_time(total_time)})")
            else:
                print(f"完成! 总用时: {self._format_time(total_time)}")


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
            print("首先统计文件总数...")

        # 首先统计总文件数以便显示进度
        total_files = 0
        for file_path in self.root_dir.rglob("*"):
            if file_path.is_file():
                total_files += 1

        if self.verbose:
            print(f"找到 {total_files} 个文件，开始筛选视频文件...")

        # 创建进度显示器
        progress = ProgressDisplay(total_files, "扫描文件", self.verbose)

        processed_files = 0
        video_count = 0

        for file_path in self.root_dir.rglob("*"):
            if file_path.is_file():
                processed_files += 1
                progress.update(1, file_path.name)

                if file_path.suffix.lower() in self.extensions:
                    try:
                        file_size = file_path.stat().st_size
                        video_file = VideoFile(
                            path=str(file_path), size=file_size, name=file_path.name
                        )
                        self.video_files.append(video_file)
                        video_count += 1

                    except (OSError, PermissionError) as e:
                        if self.verbose:
                            print(f"\n无法访问文件 {file_path}: {e}")

        progress.finish(f"扫描完成，共找到 {video_count} 个视频文件")

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
        self,
        file_path: str,
        extract_seconds: float = 5.0,
    ) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """提取视频中间位置后5秒内的帧

        Args:
            file_path: 视频文件路径
            extract_seconds: 提取多少秒的帧（固定为5秒）
            frame_position: 提取位置（现在固定为"middle"）

        Returns:
            Tuple[middle_frames, empty_list]: 中间位置帧列表和空列表（保持接口兼容）
        """
        middle_frames = []
        empty_frames = []
        try:
            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                if self.verbose:
                    print(f"无法打开视频文件: {file_path}")
                return middle_frames, empty_frames

            # 获取视频信息
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0

            if duration < 10:  # 视频太短（少于10秒），无法取中间位置后5秒
                if self.verbose:
                    print(f"视频时长过短 ({duration:.1f}秒)，跳过: {file_path}")
                return middle_frames, empty_frames

            # 计算中间位置（视频总时长的一半）
            middle_time = duration / 2
            middle_frame = int(middle_time * fps)

            # 从中间位置开始提取后5秒的帧
            target_frames = int(fps * extract_seconds) if fps > 0 else 150  # 5秒约150帧

            # 设置起始位置为中间帧
            cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
            frame_count = 0

            while frame_count < target_frames:
                ret, frame = cap.read()
                if not ret:
                    break

                # 将帧转换为灰度图像并调整大小以提高比较效率
                gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                resized_frame = cv2.resize(gray_frame, (64, 64))
                middle_frames.append(resized_frame)
                frame_count += 1

            cap.release()

        except Exception as e:
            if self.verbose:
                print(f"提取视频帧失败 {file_path}: {e}")

        return middle_frames, empty_frames

    def calculate_frame_hash(
        self, middle_frames: List[np.ndarray], empty_frames: List[np.ndarray]
    ) -> str:
        """计算中间位置帧序列的哈希值"""
        if not middle_frames:
            return ""

        try:
            # 使用中间位置的帧计算哈希值
            combined_frames = np.concatenate(
                [frame.flatten() for frame in middle_frames]
            )
            # 计算哈希值
            hasher = hashlib.md5()
            hasher.update(combined_frames.tobytes())
            return hasher.hexdigest()
        except Exception:
            return ""

    def calculate_frame_similarity(
        self,
        middle_frames1: List[np.ndarray],
        empty_frames1: List[np.ndarray],
        middle_frames2: List[np.ndarray],
        empty_frames2: List[np.ndarray],
    ) -> float:
        """计算两个视频中间位置帧序列的相似度"""
        if not middle_frames1 or not middle_frames2:
            return 0.0

        # 计算中间位置帧的相似度
        min_frame_len = min(len(middle_frames1), len(middle_frames2))
        similarities = []

        for i in range(min_frame_len):
            try:
                correlation = cv2.matchTemplate(
                    middle_frames1[i], middle_frames2[i], cv2.TM_CCOEFF_NORMED
                )[0][0]
                similarities.append(max(0, correlation))
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

        # 创建进度显示器
        progress = ProgressDisplay(total_files, "计算哈希值", self.verbose)

        for video_file in self.video_files:
            progress.update(1, video_file.name)
            video_file.hash_md5 = self.calculate_file_hash(video_file.path)
            if video_file.hash_md5:
                hash_groups[video_file.hash_md5].append(video_file)

        # 只返回有重复的组
        duplicates = {
            hash_val: files for hash_val, files in hash_groups.items() if len(files) > 1
        }

        progress.finish(f"哈希计算完成，找到 {len(duplicates)} 组哈希值相同的文件")
        return duplicates

    def detect_by_name_similarity(
        self, similarity_threshold: float = 0.8
    ) -> Dict[str, List[VideoFile]]:
        """基于文件名相似度检测可能重复的文件"""
        if self.verbose:
            print(f"正在基于文件名相似度检测 (阈值: {similarity_threshold})...")

        similar_groups = defaultdict(list)
        processed = set()
        total_files = len(self.video_files)

        # 创建进度显示器
        progress = ProgressDisplay(total_files, "比较文件名", self.verbose)

        for i, file1 in enumerate(self.video_files):
            progress.update(1, file1.name)

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

        progress.finish(f"文件名比较完成，找到 {len(duplicates)} 组名称相似的文件")
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

        # 创建进度显示器
        progress = ProgressDisplay(total_files, "获取视频时长", self.verbose)

        for video_file in self.video_files:
            progress.update(1, video_file.name)

            duration = self.get_video_duration(video_file.path)
            if duration > 0:
                video_file.duration = duration
                valid_files.append(video_file)
            elif self.verbose:
                print(f"\n跳过无法获取时长的文件: {video_file.path}")

        progress.finish(f"成功获取 {len(valid_files)} 个文件的时长信息")

        # 根据时长分组（考虑容差）
        if self.verbose:
            print("正在根据时长分组...")

        duration_groups = defaultdict(list)
        processed = set()

        # 创建分组进度显示器
        group_progress = ProgressDisplay(len(valid_files), "时长分组", self.verbose)

        for i, file1 in enumerate(valid_files):
            group_progress.update(1, file1.name)

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

        group_progress.finish(f"时长分组完成，找到 {len(duplicates)} 组时长相近的文件")
        return duplicates

    def detect_by_duration_and_frames(
        self,
        duration_tolerance: float = 3.0,
        frame_similarity_threshold: float = 0.8,
        extract_seconds: float = 5.0,
    ) -> Dict[str, List[VideoFile]]:
        """基于视频时长和中间位置画面检测重复文件"""

        if self.verbose:
            print(
                f"正在进行时长+画面检测 (时长容差: ±{duration_tolerance}秒, 画面相似度阈值: {frame_similarity_threshold}, 提取中间位置后{extract_seconds}秒)..."
            )

        # 首先基于时长进行初步筛选
        duration_candidates = self.detect_by_duration(duration_tolerance)

        if not duration_candidates:
            if self.verbose:
                print("没有时长相近的文件，跳过画面比对")
            return {}

        # 对时长相近的文件进行画面比对
        frame_duplicates = defaultdict(list)
        total_groups = len(duration_candidates)

        # 创建组处理进度显示器
        group_progress = ProgressDisplay(total_groups, "画面比较分组", self.verbose)

        for group_key, files in duration_candidates.items():
            group_progress.update(1, f"组 {group_key}")

            if len(files) < 2:
                continue

            if self.verbose:
                print(f"\n正在处理组 {group_key} ({len(files)} 个文件)")

            # 提取每个文件中间位置的帧
            file_frames = {}

            # 创建帧提取进度显示器
            frame_progress = ProgressDisplay(
                len(files), f"  提取中间位置帧 ({group_key})", self.verbose
            )

            for video_file in files:
                frame_progress.update(1, video_file.name)
                middle_frames, empty_frames = self.extract_video_frames(
                    video_file.path, extract_seconds
                )
                if middle_frames:
                    file_frames[video_file.path] = (
                        video_file,
                        middle_frames,
                        empty_frames,
                    )

            frame_progress.finish("帧提取完成")

            # 比较画面相似度
            processed_files = set()
            similar_group_count = 0
            total_comparisons = len(file_frames) * (len(file_frames) - 1) // 2

            if total_comparisons > 0:
                similarity_progress = ProgressDisplay(
                    total_comparisons, f"  相似度比较 ({group_key})", self.verbose
                )
                comparison_count = 0

                for path1, (
                    file1,
                    middle_frames1,
                    empty_frames1,
                ) in file_frames.items():
                    if path1 in processed_files:
                        continue

                    similar_files = [file1]
                    processed_files.add(path1)

                    for path2, (
                        file2,
                        middle_frames2,
                        empty_frames2,
                    ) in file_frames.items():
                        if path2 in processed_files:
                            continue

                        comparison_count += 1
                        similarity_progress.update(1, f"{file1.name} vs {file2.name}")

                        similarity = self.calculate_frame_similarity(
                            middle_frames1, empty_frames1, middle_frames2, empty_frames2
                        )
                        if self.verbose:
                            print(
                                f"\n    中间位置相似度 {file1.name} vs {file2.name}: {similarity:.3f}"
                            )

                        if similarity >= frame_similarity_threshold:
                            similar_files.append(file2)
                            processed_files.add(path2)

                    if len(similar_files) > 1:
                        frame_group_key = f"{group_key}_frames_{similar_group_count}"
                        frame_duplicates[frame_group_key] = similar_files
                        similar_group_count += 1

                similarity_progress.finish("相似度比较完成")

        group_progress.finish(
            f"画面比较完成，找到 {len(frame_duplicates)} 组画面相似的文件"
        )

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

        # 计算总的要删除的文件数
        total_to_delete = 0
        for group_key, files in duplicates.items():
            if len(files) > 1:
                total_to_delete += len(files) - 1  # 保留最大的，删除其余的

        if total_to_delete == 0:
            if self.verbose:
                print("没有重复文件需要删除")
            return 0, 0

        # 创建删除进度显示器
        action_name = "模拟删除" if dry_run else "删除文件"
        progress = ProgressDisplay(total_to_delete, action_name, self.verbose)

        for group_key, files in duplicates.items():
            if len(files) <= 1:
                continue

            # 按文件大小排序，保留最大的
            sorted_files = sorted(files, key=lambda x: x.size, reverse=True)
            files_to_delete = sorted_files[1:]  # 除了第一个（最大文件）之外的所有文件

            for file in files_to_delete:
                progress.update(1, file.name)
                try:
                    if dry_run:
                        if self.verbose:
                            print(f"\n[模拟] 将删除: {file.path}")
                    else:
                        os.remove(file.path)
                        if self.verbose:
                            print(f"\n[已删除] {file.path}")
                    deleted_count += 1
                except OSError as e:
                    if self.verbose:
                        print(f"\n[删除失败] {file.path}: {e}")
                    failed_count += 1

        progress.finish(
            f"{'模拟' if dry_run else ''}删除完成: {deleted_count} 个文件, {failed_count} 个失败"
        )
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
        "--extract-seconds",
        type=float,
        default=5.0,
        help="提取视频前后多少秒的帧进行比较 (默认: 5.0)",
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
    print(f"\n{'='*60}")
    print(f"开始重复文件检测 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"检测方法: {args.method}")
    print(f"文件总数: {len(detector.video_files)}")
    print(f"{'='*60}")

    all_duplicates = {}
    detection_start_time = time.time()

    # 计算需要执行的检测方法数量
    methods_to_run = []
    if args.method in ["size", "all"]:
        methods_to_run.append("size")
    if args.method in ["hash", "all"]:
        methods_to_run.append("hash")
    if args.method in ["name", "all"]:
        methods_to_run.append("name")
    if args.method in ["duration", "all"]:
        methods_to_run.append("duration")
    if args.method in ["frames", "all"]:
        methods_to_run.append("frames")

    total_methods = len(methods_to_run)
    current_method = 0

    if args.method in ["size", "all"]:
        current_method += 1
        print(f"\n[{current_method}/{total_methods}] 开始文件大小检测...")
        duplicates = detector.detect_by_size()
        all_duplicates["文件大小"] = duplicates
        detector.print_duplicates_report(duplicates, "文件大小")

    if args.method in ["hash", "all"]:
        current_method += 1
        print(f"\n[{current_method}/{total_methods}] 开始哈希值检测...")
        duplicates = detector.detect_by_hash()
        all_duplicates["哈希值"] = duplicates
        detector.print_duplicates_report(duplicates, "哈希值")

    if args.method in ["name", "all"]:
        current_method += 1
        print(f"\n[{current_method}/{total_methods}] 开始文件名相似度检测...")
        duplicates = detector.detect_by_name_similarity(args.similarity)
        all_duplicates["文件名相似度"] = duplicates
        detector.print_duplicates_report(duplicates, "文件名相似度")

    if args.method in ["duration", "all"]:
        current_method += 1
        print(f"\n[{current_method}/{total_methods}] 开始视频时长检测...")
        duplicates = detector.detect_by_duration(args.duration_tolerance)
        all_duplicates["视频时长"] = duplicates
        detector.print_duplicates_report(duplicates, "视频时长")

    if args.method in ["frames", "all"]:
        current_method += 1
        print(f"\n[{current_method}/{total_methods}] 开始时长+画面检测...")
        duplicates = detector.detect_by_duration_and_frames(
            args.duration_tolerance,
            args.frame_similarity,
            args.extract_seconds,
        )
        all_duplicates["时长+画面"] = duplicates
        detector.print_duplicates_report(duplicates, "时长+画面")

    # 显示总体检测完成信息
    total_detection_time = time.time() - detection_start_time
    print(f"\n{'='*60}")
    print(f"检测完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"总用时: {total_detection_time/60:.1f} 分钟 ({total_detection_time:.1f} 秒)")
    print(f"{'='*60}")

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
