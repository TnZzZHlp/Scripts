import os
import shutil
import subprocess
import sys
import tempfile
import time
import stat
import contextlib

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

            log_path = os.path.join(log_folder, "backup", "komga.txt")
            LOG_FILE = open(log_path, "w", encoding="utf-8")

    timestamp = time.ctime()
    formatted_message = f"{timestamp}: {message}"

    # 写入日志文件
    if LOG_FILE:
        LOG_FILE.write(f"{formatted_message}\n")
        LOG_FILE.flush()  # 立即写入文件

    print(formatted_message)


def close_log_file():
    """关闭日志文件"""
    global LOG_FILE
    if LOG_FILE:
        try:
            LOG_FILE.close()
        except IOError as e:
            print(f"错误: 关闭日志文件时出错: {e}")
        finally:
            LOG_FILE = None


def set_writable_permissions(path):
    """递归设置目录中所有文件为可写，记录错误但不中断"""
    permission_errors = []
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            item_path = os.path.join(root, name)
            try:
                # 尝试设置更宽松的权限，确保所有者可读写执行，组和其他用户可读写
                current_stat = os.stat(item_path)
                # 添加写权限给所有者、组和其他用户
                new_mode = (
                    current_stat.st_mode | stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
                )
                os.chmod(item_path, new_mode)
            except FileNotFoundError:
                # 文件可能在遍历过程中被删除，记录并跳过
                error_msg = f"修改权限时文件未找到: {item_path}"
                log(error_msg)
                permission_errors.append(error_msg)
            except (OSError, PermissionError) as e:
                error_msg = f"无法修改权限 {item_path}: {e}"
                log(error_msg)
                permission_errors.append(error_msg)

    if permission_errors:
        log(f"在设置权限时遇到 {len(permission_errors)} 个错误。")
    return not bool(permission_errors)  # 如果没有错误返回True，否则返回False


def run_command(command, error_message_prefix):
    """运行外部命令并处理错误"""
    log(f"执行命令: {' '.join(command)}")
    try:
        result = subprocess.run(
            command,
            check=True,  # 失败时抛出 CalledProcessError
            capture_output=True,  # 捕获 stdout 和 stderr
            text=True,  # 以文本模式处理输出
            encoding="utf-8",  # 指定编码
            errors="replace",  # 处理无法解码的字符
        )
        log(f"命令成功完成: {' '.join(command)}")
        if result.stdout:
            log(f"命令输出 (stdout):\n{result.stdout.strip()}")
        if result.stderr:
            log(
                f"命令输出 (stderr):\n{result.stderr.strip()}"
            )  # 有些工具会把进度信息输出到stderr
        return True
    except FileNotFoundError:
        log(f"错误: 命令未找到: {command[0]}. 请确保它在系统 PATH 中或提供了完整路径。")
        raise  # 重新抛出以便上层捕获
    except subprocess.CalledProcessError as e:
        log(f"错误: {error_message_prefix} 失败 (返回码: {e.returncode})")
        if e.stdout:
            log(f"命令输出 (stdout):\n{e.stdout.strip()}")
        if e.stderr:
            log(f"命令错误输出 (stderr):\n{e.stderr.strip()}")
        raise  # 重新抛出以便上层捕获
    except Exception as e:  # 捕获其他可能的异常
        log(f"错误: 执行命令时发生意外错误 {' '.join(command)}: {e}")
        raise  # 重新抛出


def main(source_directory, backup_type):
    """
    source_directory: qBittorrent的配置文件目录
    backup_type: 备份qBittorrent类型 (用于命名临时文件和压缩包)
    """
    log(f"开始备份qBittorrent ({backup_type})")
    tmp_folder = None  # 初始化为 None
    compressed_file = None  # 初始化为 None

    try:
        # 生成临时文件和目录名
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        base_name = f"qbittorrent_backup_{backup_type}_{timestamp_str}"
        tmp_folder = os.path.join(tempfile.gettempdir(), base_name)
        compressed_file = os.path.join(tempfile.gettempdir(), f"{base_name}.7z")

        # 1. 创建临时文件夹并复制文件
        log(f"创建临时文件夹并复制源目录: {source_directory} -> {tmp_folder}")
        try:
            shutil.copytree(source_directory, tmp_folder)
        except FileNotFoundError:
            log(f"错误: 源目录不存在: {source_directory}")
            raise  # 重新抛出，终止执行
        except PermissionError:
            log(f"错误: 没有权限读取源目录: {source_directory}")
            raise
        except shutil.Error as e:
            log(f"错误: 复制文件时出错: {e}")
            raise

        # 2. 修改所有文件权限为可写 (可选，如果失败仅记录日志)
        log("尝试更新临时文件夹中的文件权限...")
        set_writable_permissions(tmp_folder)  # 记录错误，但不因此中断

        # 3. 删除不需要的文件
        log("删除临时文件夹中的临时数据库文件和日志...")
        files_to_remove = [
            os.path.join(tmp_folder, "data", "torrents.db-shm"),
            os.path.join(tmp_folder, "data", "torrents.db-wal"),
        ]
        folder_to_remove = os.path.join(tmp_folder, "data", "logs")

        for file_path in files_to_remove:
            with contextlib.suppress(FileNotFoundError):  # 忽略文件不存在的错误
                try:
                    os.remove(file_path)
                    log(f"已删除文件: {file_path}")
                except (OSError, PermissionError) as e:
                    log(f"警告: 删除文件失败 {file_path}: {e}")  # 记录错误但继续

        if os.path.exists(folder_to_remove):
            try:
                shutil.rmtree(folder_to_remove)
                log(f"已删除文件夹: {folder_to_remove}")
            except (OSError, PermissionError) as e:
                log(f"警告: 删除文件夹失败 {folder_to_remove}: {e}")  # 记录错误但继续

        # 4. 使用7z压缩目录
        log(f"压缩目录: {tmp_folder} -> {compressed_file}")
        # 确保 7z.exe 在 PATH 中或提供完整路径
        # 假设 7z.exe 在 PATH 中
        seven_zip_command = ["7z", "a", "-t7z", "-mx9", compressed_file, tmp_folder]
        run_command(seven_zip_command, "压缩文件")
        log("压缩文件完成")

        # 5. 使用rclone上传到远程
        log(f"上传文件: {compressed_file}")
        # 假设 rclone.exe 在 PATH 中，或者提供完整路径
        # 使用环境变量或配置文件管理 rclone 路径和目标地址可能更佳
        rclone_path = os.getenv(
            "RCLONE_PATH", "rclone"
        )  # 尝试从环境变量获取路径，否则使用 'rclone'
        rclone_target = os.getenv(
            "RCLONE_TARGET_QB", "b2:tnzzzhlpbackup/qbittorrent/"
        )  # 目标地址
        rclone_command = [rclone_path, "copy", compressed_file, rclone_target]
        run_command(rclone_command, "上传文件")
        log("上传文件完成")

        log(f"qBittorrent ({backup_type}) 备份成功完成！")

    except (
        FileNotFoundError,
        PermissionError,
        shutil.Error,
        subprocess.CalledProcessError,
    ) as e:
        # 捕获预期的、由我们自己处理并重新抛出的异常
        log(f"备份过程中断: {e}")
        # 这里可以添加发送通知等操作
        sys.exit(1)  # 以非零状态码退出，表示失败
    except Exception as e:
        # 捕获所有其他意外错误
        log(f"发生意外错误: {e}")
        import traceback

        log(f"Traceback:\n{traceback.format_exc()}")
        sys.exit(1)  # 以非零状态码退出

    finally:
        # 清理操作
        log("开始清理临时文件...")
        if tmp_folder and os.path.exists(tmp_folder):
            try:
                log(f"正在删除临时文件夹: {tmp_folder}")
                # 在删除前再次尝试设置权限，应对可能的权限问题
                set_writable_permissions(tmp_folder)
                shutil.rmtree(tmp_folder)
                log("临时文件夹已删除")
            except (OSError, PermissionError, shutil.Error) as e:
                log(f"清理临时文件夹失败: {tmp_folder}: {e}")  # 记录具体错误

        if compressed_file and os.path.exists(compressed_file):
            try:
                log(f"正在删除临时压缩文件: {compressed_file}")
                os.remove(compressed_file)
                log("临时压缩文件已删除")
            except (OSError, PermissionError) as e:
                log(f"清理临时压缩文件失败: {compressed_file}: {e}")  # 记录具体错误

        close_log_file()  # 确保日志文件在脚本结束时关闭
        log("清理完成。")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("错误: 请提供源目录路径和备份类型作为命令行参数。")
        print("用法: python qbittorrent.py <source_directory> <backup_type>")
        exit(1)

    source_directory_arg = sys.argv[1]
    backup_type_arg = sys.argv[2]

    # 增加对源目录的检查
    if not os.path.isdir(source_directory_arg):  # 检查是否是目录
        print(f"错误: 提供的源路径不是一个有效的目录: {source_directory_arg}")
        exit(1)

    main(source_directory_arg, backup_type_arg)
