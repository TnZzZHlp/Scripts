import os
import subprocess
import argparse
from pathlib import Path
from tqdm import tqdm
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def find_mkv_files(directory):
    """查找指定目录下的所有mkv文件"""
    mkv_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(".mkv"):
                mkv_files.append(os.path.join(root, file))
    return mkv_files


def convert_mkv_to_mp4(input_file, output_file, keep_original=False):
    """使用ffmpeg将mkv文件转换为mp4"""
    try:
        # 构建ffmpeg命令
        cmd = [
            "ffmpeg",
            "-i",
            input_file,
            "-c",
            "copy",  # 直接复制流，不重新编码（速度快）
            "-y",  # 覆盖输出文件
            output_file,
        ]

        logging.info(f"开始转换: {os.path.basename(input_file)}")

        # 执行转换
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore"
        )

        if result.returncode == 0:
            logging.info(f"转换成功: {os.path.basename(output_file)}")

            # 如果不保留原文件，删除mkv文件
            if not keep_original:
                os.remove(input_file)
                logging.info(f"已删除原文件: {os.path.basename(input_file)}")

            return True
        else:
            logging.error(f"转换失败: {os.path.basename(input_file)}")
            logging.error(f"错误信息: {result.stderr}")
            return False

    except Exception as e:
        logging.error(f"转换 {input_file} 时发生错误: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="将指定目录下的所有mkv文件转换为mp4")
    parser.add_argument("directory", help="包含mkv文件的目录路径")
    parser.add_argument(
        "--keep-original",
        "-k",
        action="store_true",
        help="保留原mkv文件（默认转换后删除）",
    )
    parser.add_argument("--output-dir", "-o", help="输出目录（默认与输入文件相同目录）")

    args = parser.parse_args()

    # 检查目录是否存在
    if not os.path.exists(args.directory):
        logging.error(f"目录不存在: {args.directory}")
        return

    # 检查ffmpeg是否可用
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.error("ffmpeg未找到，请确保已安装ffmpeg并添加到PATH环境变量")
        return

    # 查找所有mkv文件
    logging.info(f"正在扫描目录: {args.directory}")
    mkv_files = find_mkv_files(args.directory)

    if not mkv_files:
        logging.info("未找到mkv文件")
        return

    logging.info(f"找到 {len(mkv_files)} 个mkv文件")

    # 转换文件
    successful = 0
    failed = 0

    for mkv_file in tqdm(mkv_files, desc="转换进度"):
        # 生成输出文件路径
        if args.output_dir:
            # 保持相对路径结构
            rel_path = os.path.relpath(mkv_file, args.directory)
            output_file = os.path.join(args.output_dir, rel_path)
            output_file = output_file.rsplit(".", 1)[0] + ".mp4"

            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
        else:
            # 在原目录生成mp4文件
            output_file = mkv_file.rsplit(".", 1)[0] + ".mp4"

        # 跳过已存在的mp4文件
        if os.path.exists(output_file):
            logging.info(f"跳过已存在的文件: {os.path.basename(output_file)}")
            continue

        # 转换文件
        if convert_mkv_to_mp4(mkv_file, output_file, args.keep_original):
            successful += 1
        else:
            failed += 1

    # 输出统计信息
    logging.info(f"转换完成! 成功: {successful}, 失败: {failed}")


if __name__ == "__main__":
    main()
