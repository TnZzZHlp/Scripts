#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qBittorrent Linux路径长度检查工具
检查qBittorrent中的种子文件路径是否超过Linux路径长度限制(4096字节)
"""
import os
import time
import requests

QB_ADDRESS = "http://192.168.2.10:8080"  # qBittorrent WebUI地址
MAX_PATH_LENGTH = 210  # Linux路径长度限制 (PATH_MAX)

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
            os.makedirs(os.path.join(log_folder, "qB"), exist_ok=True)

            log_path = os.path.join(log_folder, "qB", "check_path_length.txt")
            LOG_FILE = open(log_path, "a", encoding="utf-8")

    timestamp = time.ctime()
    formatted_message = f"{timestamp}: {message}"

    # 写入日志文件
    if LOG_FILE:
        LOG_FILE.write(f"{formatted_message}\n")
        LOG_FILE.flush()  # 立即写入文件

    print(formatted_message)


def check_path_length(save_path, file_name):
    """检查文件路径长度是否超过Linux限制"""
    # 正确处理路径拼接，考虑文件可能包含子目录路径
    full_path = os.path.normpath(os.path.join(save_path, file_name))
    path_length = len(full_path)

    if path_length > MAX_PATH_LENGTH:
        return True, path_length, full_path
    return False, path_length, full_path


def main():
    """
    主函数：检查qBittorrent中所有种子的文件路径长度
    """
    try:
        # 获取qBittorrent中的所有种子
        response = requests.get(f"{QB_ADDRESS}/api/v2/torrents/info")
        response.raise_for_status()
        torrents = response.json()
        log(f"获取到 {len(torrents)} 个种子")

        long_path_count = 0
        total_files_checked = 0

        for torrent in torrents:
            torrent_hash = torrent["hash"]
            torrent_name = torrent["name"]
            save_path = torrent["save_path"]

            # 获取种子的文件列表
            response = requests.get(
                f"{QB_ADDRESS}/api/v2/torrents/files?hash={torrent_hash}"
            )
            response.raise_for_status()
            files = response.json()

            log(f"检查种子: {torrent_name} ({len(files)} 个文件)")

            for file_info in files:
                file_name = file_info["name"]
                is_too_long, path_length, full_path = check_path_length(
                    save_path, file_name
                )
                total_files_checked += 1

                if is_too_long:
                    long_path_count += 1
                    log(f"⚠️ 路径过长: {path_length} 字符 (限制: {MAX_PATH_LENGTH})")
                    log(f"   种子: {torrent_name}")
                    log(f"   文件: {file_name}")
                    log(f"   保存路径: {save_path}")
                    log(f"   完整路径: {full_path}")
                    log("   " + "-" * 50)

        # 输出总结信息
        log("\n" + "=" * 60)
        log(f"检查完成! 总共检查了 {total_files_checked} 个文件")
        log(f"发现 {long_path_count} 个文件的路径超过了 {MAX_PATH_LENGTH} 字符限制")
        log("=" * 60)

    except requests.exceptions.ConnectionError:
        log("错误: 无法连接到 qBittorrent WebUI")
        log(f"请检查 qBittorrent 是否运行在 {QB_ADDRESS}")
    except requests.exceptions.RequestException as e:
        log(f"网络请求错误: {e}")
    except Exception as e:
        log(f"检查过程出现错误: {e}")


if __name__ == "__main__":
    main()
