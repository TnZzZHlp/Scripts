#!/usr/bin/env python3
"""
视频分辨率检测和转换脚本
功能：检测指定文件夹下的所有视频文件，如果分辨率大于4K则转换为4K H265格式
使用AMD硬件编码加速(AMF)
"""

import os
import sys
import subprocess
import json
import argparse
from pathlib import Path
import logging
from typing import Tuple, Optional, List
import tqdm  # 添加 tqdm 库用于显示进度

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# 支持的视频文件扩展名
VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
    ".3gp",
    ".ts",
    ".mts",
}

# 4K分辨率定义 (3840x2160)
TARGET_4K_WIDTH = 3840
TARGET_4K_HEIGHT = 2160


class VideoConverter:
    def __init__(
        self,
        input_folder: str,
        output_folder: Optional[str] = None,
        dry_run: bool = False,
    ):
        """
        初始化视频转换器

        Args:
            input_folder: 输入文件夹路径
            output_folder: 输出文件夹路径，如果为None则在原文件夹创建converted子文件夹
            dry_run: 是否为预览模式，不实际执行转换
        """
        self.input_folder = Path(input_folder)
        self.output_folder = (
            Path(output_folder) if output_folder else self.input_folder / "converted"
        )
        self.dry_run = dry_run

        if not self.input_folder.exists():
            raise ValueError(f"输入文件夹不存在: {self.input_folder}")

        # 创建输出文件夹
        if not self.dry_run:
            self.output_folder.mkdir(parents=True, exist_ok=True)

    def check_ffmpeg(self) -> bool:
        """检查ffmpeg是否可用"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                logger.info("FFmpeg检查通过")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        logger.error("FFmpeg未找到或不可用，请确保FFmpeg已安装并添加到PATH")
        return False

    def get_video_info(self, video_path: Path) -> Optional[dict]:
        """
        获取视频文件信息

        Args:
            video_path: 视频文件路径

        Returns:
            包含视频信息的字典，失败时返回None
        """
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(video_path),
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, encoding="utf-8"
            )

            if result.returncode != 0 or not result.stdout.strip():
                logger.warning(f"无法获取视频信息: {video_path}")
                return None

            return json.loads(result.stdout)

        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            logger.error(f"获取视频信息时出错 {video_path}: {e}")
            return None

    def get_video_resolution(self, video_info: dict) -> Optional[Tuple[int, int]]:
        """
        从视频信息中提取分辨率

        Args:
            video_info: ffprobe返回的视频信息

        Returns:
            (width, height) 元组，失败时返回None
        """
        try:
            for stream in video_info.get("streams", []):
                if stream.get("codec_type") == "video":
                    width = stream.get("width")
                    height = stream.get("height")
                    if width and height:
                        return (int(width), int(height))
            return None
        except Exception as e:
            logger.error(f"解析视频分辨率时出错: {e}")
            return None

    def needs_conversion(self, width: int, height: int) -> bool:
        """
        判断是否需要转换（分辨率是否大于4K）

        Args:
            width: 视频宽度
            height: 视频高度

        Returns:
            True如果需要转换，False否则
        """
        return width > TARGET_4K_WIDTH or height > TARGET_4K_HEIGHT

    def calculate_target_resolution(self, width: int, height: int) -> Tuple[int, int]:
        """
        计算目标分辨率，保持宽高比

        Args:
            width: 原始宽度
            height: 原始高度

        Returns:
            (target_width, target_height) 元组
        """
        aspect_ratio = width / height

        if aspect_ratio > (TARGET_4K_WIDTH / TARGET_4K_HEIGHT):
            # 宽度为主要限制因素
            target_width = TARGET_4K_WIDTH
            target_height = int(TARGET_4K_WIDTH / aspect_ratio)
            # 确保高度为偶数
            target_height = target_height - (target_height % 2)
        else:
            # 高度为主要限制因素
            target_height = TARGET_4K_HEIGHT
            target_width = int(TARGET_4K_HEIGHT * aspect_ratio)
            # 确保宽度为偶数
            target_width = target_width - (target_width % 2)

        return (target_width, target_height)

    def convert_video(
        self, input_path: Path, output_path: Path, target_width: int, target_height: int
    ) -> bool:
        """
        转换视频文件

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            target_width: 目标宽度
            target_height: 目标高度

        Returns:
            转换成功返回True，失败返回False
        """
        if self.dry_run:
            logger.info(
                f"[预览模式] 将转换: {input_path} -> {output_path} ({target_width}x{target_height})"
            )
            return True

        try:
            # 构建ffmpeg命令
            cmd = [
                "ffmpeg",
                "-i",
                str(input_path),
                "-c:v",
                "hevc_amf",  # AMD AMF硬件编码器
                "-quality",
                "balanced",  # AMD AMF质量设置
                "-rc",
                "vbr_peak",  # 可变比特率
                "-qp_i",
                "22",  # I帧量化参数
                "-qp_p",
                "24",  # P帧量化参数
                "-qp_b",
                "26",  # B帧量化参数
                "-vf",
                f"scale={target_width}:{target_height}",  # 缩放滤镜
                "-c:a",
                "copy",  # 音频直接复制
                "-movflags",
                "+faststart",  # 优化MP4文件
                "-y",  # 覆盖输出文件
                str(output_path),
            ]

            logger.info(f"开始转换: {input_path.name}")
            logger.debug(f"FFmpeg命令: {' '.join(cmd)}")

            # 执行转换
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=3600  # 1小时超时
            )

            if result.returncode == 0:
                logger.info(f"转换成功: {input_path.name} -> {output_path.name}")
                return True
            else:
                logger.error(f"转换失败: {input_path.name}")
                logger.error(f"FFmpeg错误: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"转换超时: {input_path.name}")
            return False
        except Exception as e:
            logger.error(f"转换时出现异常 {input_path.name}: {e}")
            return False

    def find_video_files(self) -> List[Path]:
        """
        查找所有视频文件

        Returns:
            视频文件路径列表
        """
        video_files = []

        for file_path in self.input_folder.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in VIDEO_EXTENSIONS:
                video_files.append(file_path)

        return video_files

    def process_videos(self):
        """处理所有视频文件"""
        if not self.check_ffmpeg():
            return

        video_files = self.find_video_files()

        if not video_files:
            logger.info("未找到视频文件")
            return

        logger.info(f"找到 {len(video_files)} 个视频文件")

        converted_count = 0
        skipped_count = 0
        failed_count = 0

        # 使用 tqdm 显示进度条
        for video_file in tqdm.tqdm(video_files, desc="处理视频文件", unit="file"):
            logger.info(f"处理文件: {video_file.name}")

            # 获取视频信息
            video_info = self.get_video_info(video_file)
            if not video_info:
                logger.warning(f"跳过文件（无法获取信息）: {video_file.name}")
                failed_count += 1
                continue

            # 获取分辨率
            resolution = self.get_video_resolution(video_info)
            if not resolution:
                logger.warning(f"跳过文件（无法获取分辨率）: {video_file.name}")
                failed_count += 1
                continue

            width, height = resolution
            logger.info(f"当前分辨率: {width}x{height}")

            # 检查是否需要转换
            if not self.needs_conversion(width, height):
                logger.info(f"跳过文件（分辨率已符合要求）: {video_file.name}")
                skipped_count += 1
                continue

            # 计算目标分辨率
            target_width, target_height = self.calculate_target_resolution(
                width, height
            )
            logger.info(f"目标分辨率: {target_width}x{target_height}")

            # 生成输出文件路径
            relative_path = video_file.relative_to(self.input_folder)
            output_path = self.output_folder / relative_path.with_suffix(".mp4")

            # 创建输出目录
            if not self.dry_run:
                output_path.parent.mkdir(parents=True, exist_ok=True)

            # 转换视频
            if self.convert_video(video_file, output_path, target_width, target_height):
                converted_count += 1
            else:
                failed_count += 1

        # 输出统计信息
        logger.info("=" * 50)
        logger.info("处理完成!")
        logger.info(f"转换成功: {converted_count} 个文件")
        logger.info(f"跳过: {skipped_count} 个文件")
        logger.info(f"失败: {failed_count} 个文件")
        logger.info(f"总计: {len(video_files)} 个文件")


def main():
    parser = argparse.ArgumentParser(
        description="检测并转换大于4K分辨率的视频文件为4K H265格式(AMD硬件编码)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python convert_4k_h265_amd.py /path/to/videos
  python convert_4k_h265_amd.py /path/to/videos -o /path/to/output
  python convert_4k_h265_amd.py /path/to/videos --dry-run
        """,
    )

    parser.add_argument("input_folder", help="输入视频文件夹路径")

    parser.add_argument(
        "-o",
        "--output",
        help="输出文件夹路径（默认在输入文件夹下创建converted子文件夹）",
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="预览模式，只检测不实际转换"
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        converter = VideoConverter(
            input_folder=args.input_folder,
            output_folder=args.output,
            dry_run=args.dry_run,
        )

        converter.process_videos()

    except KeyboardInterrupt:
        logger.info("用户中断操作")
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
