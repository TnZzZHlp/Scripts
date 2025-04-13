import os
import shutil
import subprocess
import sys
import tempfile
import time
import stat

JELLYFIN_DIR = "C:/Jellyfin"

# 定义全局变量用于存储日志文件描述符
LOG_FILE = None


def log(message):
    """日志记录函数"""
    global LOG_FILE

    # 如果日志文件还未初始化，尝试初始化
    log_folder = os.getenv("LOG_FOLDER")
    if LOG_FILE is None and isinstance(log_folder, str):
        if os.path.exists(log_folder):
            # 确保日志文件夹存在
            os.makedirs(os.path.join(log_folder, "backup"), exist_ok=True)

            # 以追加模式打开日志文件
            log_path = os.path.join(log_folder, "backup", "jellyfin.txt")
            LOG_FILE = open(log_path, "w", encoding="utf-8")

    timestamp = time.ctime()
    formatted_message = f"{timestamp}: {message}"

    # 写入日志文件
    if LOG_FILE:
        LOG_FILE.write(f"{formatted_message}\n")
        LOG_FILE.flush()  # 立即写入文件

    print(formatted_message)


def set_writable_permissions(path):
    """递归设置目录中所有文件为可写"""
    for root, dirs, files in os.walk(path):
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            os.chmod(dir_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)  # 777权限

        for file_name in files:
            file_path = os.path.join(root, file_name)
            try:
                os.chmod(
                    file_path,
                    stat.S_IRUSR
                    | stat.S_IWUSR
                    | stat.S_IRGRP
                    | stat.S_IWGRP
                    | stat.S_IROTH,
                )  # 664权限
            except Exception as e:
                log(f"无法修改文件权限 {file_path}: {e}")


def main():
    log("开始备份Jellyfin")
    # 获取当前系统的临时文件夹路径
    timestamp = int(time.time())
    tmp_folder = os.path.join(tempfile.gettempdir(), f"jellyfin_backup_{timestamp}")
    compressed_file = os.path.join(
        tempfile.gettempdir(), f"backup_jellyfin_{timestamp}.7z"
    )

    # 判断目标文件夹是否已存在
    if os.path.exists(tmp_folder):
        log(f"临时文件夹已存在: {tmp_folder}，退出备份")
        sys.exit(1)

    try:
        # 创建临时文件夹
        log(f"创建临时文件夹: {tmp_folder}")
        os.makedirs(tmp_folder)

        # 源文件路径和目标路径
        sources_and_destinations = [
            (f"{JELLYFIN_DIR}/Config", os.path.join(tmp_folder, "Config")),
            (
                f"{JELLYFIN_DIR}/Data/data",
                os.path.join(tmp_folder, "Data", "data"),
            ),
            (
                f"{JELLYFIN_DIR}/Data/root",
                os.path.join(tmp_folder, "Data", "root"),
            ),
            (
                f"{JELLYFIN_DIR}/Data/plugins",
                os.path.join(tmp_folder, "Data", "plugins"),
            ),
        ]

        # 复制文件到临时文件夹
        for source, destination in sources_and_destinations:
            if os.path.exists(source):
                log(f"正在复制 {source} 到 {destination}")
                shutil.copytree(source, destination)
            else:
                log(f"源路径不存在: {source}")

        # 修改所有文件权限为可写
        log("更新文件权限...")
        set_writable_permissions(tmp_folder)

        # 删除不需要备份的元数据文件夹
        metadata_path = os.path.join(tmp_folder, "Config", "metadata")
        if os.path.exists(metadata_path):
            log(f"正在删除元数据文件夹: {metadata_path}")
            shutil.rmtree(metadata_path)

        # 使用7z压缩目录
        log(f"压缩目录到: {compressed_file}")
        compress_result = subprocess.run(
            [
                "C:/Users/Administrator/scoop/shims/7z.exe",
                "a",
                "-t7z",
                compressed_file,
                tmp_folder,
            ]
        )
        if compress_result.returncode != 0:
            raise Exception("压缩文件失败，请检查7z是否安装")
        log("压缩文件完成")

        # 使用rclone上传到远程
        log("开始上传文件")
        upload_result = subprocess.run(
            [
                "C:/Users/Administrator/scoop/shims/rclone.exe",
                "copy",
                compressed_file,
                "b2:tnzzzhlpbackup/backup/jellyfin/",
            ]
        )
        if upload_result.returncode != 0:
            raise Exception("上传文件失败, 请检查rclone配置或rclone是否安装")
        log("上传文件完成")

    except Exception as e:
        log(f"备份过程中发生错误: {e}")

    finally:
        # 删除临时文件夹
        try:
            if os.path.exists(tmp_folder):
                log(f"正在删除临时文件夹: {tmp_folder}")
                shutil.rmtree(tmp_folder)
        except Exception as e:
            log(f"清理临时文件夹失败: {e}")

        # 删除临时压缩文件
        try:
            if os.path.exists(compressed_file):
                log(f"正在删除临时压缩文件: {compressed_file}")
                os.remove(compressed_file)
        except Exception as e:
            log(f"清理临时压缩文件失败: {e}")


if __name__ == "__main__":
    main()
