import os
import shutil
import subprocess
import sys
import tempfile
import time
import stat

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

            log_path = os.path.join(log_folder, "backup", "qb.txt")
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


def main(source_directory):
    log("开始备份qBittorrent")
    # 获取当前系统的临时文件夹路径
    timestamp = int(time.time())
    tmp_folder = os.path.join(tempfile.gettempdir(), f"qbittorrent_backup_{timestamp}")
    compressed_file = os.path.join(
        tempfile.gettempdir(), f"backup_qBittorrent_{timestamp}.7z"
    )

    try:
        # 创建临时文件夹并复制文件
        log(f"创建临时文件夹: {tmp_folder}")
        shutil.copytree(source_directory, tmp_folder)

        # 修改所有文件权限为可写
        log("更新文件权限...")
        set_writable_permissions(tmp_folder)

        # 删除其中的torrents.db-shm和torrents.db-wal
        shm_file = os.path.join(tmp_folder, "data", "torrents.db-shm")
        wal_file = os.path.join(tmp_folder, "data", "torrents.db-wal")
        log_folder = os.path.join(tmp_folder, "data", "logs")

        if os.path.exists(shm_file):
            os.remove(shm_file)
        if os.path.exists(wal_file):
            os.remove(wal_file)
        if os.path.exists(log_folder):
            shutil.rmtree(log_folder)

        # 使用7z压缩目录
        log(f"压缩目录到: {compressed_file}")
        compress_result = subprocess.run(
            ["7z.exe", "a", "-t7z", compressed_file, tmp_folder]
        )
        if compress_result.returncode != 0:
            raise Exception("压缩文件失败")
        log("压缩文件完成")

        # 使用rclone上传到远程
        log("开始上传文件")
        upload_result = subprocess.run(
            [
                "C:/Users/Administrator/scoop/shims/rclone.exe",
                "copy",
                compressed_file,
                "b2:tnzzzhlpbackup/qbittorrent/",
            ]
        )
        if upload_result.returncode != 0:
            raise Exception("上传文件失败")
        log("上传文件完成")

    except Exception as e:
        log(f"发生错误: {e}")

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
    if len(sys.argv) < 2:
        log("请提供源目录路径作为参数")
        exit(1)

    source_directory = sys.argv[1]
    if not os.path.exists(source_directory):
        log(f"源目录不存在: {source_directory}")
        exit(1)

    main(source_directory)
