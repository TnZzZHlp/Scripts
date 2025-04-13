import os
import time
import requests

QB_ADDRESS = "http://192.168.2.10:8080"


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

            log_path = os.path.join(log_folder, "backup", "jellyfin.txt")
            LOG_FILE = open(log_path, "w", encoding="utf-8")

    timestamp = time.ctime()
    formatted_message = f"{timestamp}: {message}"

    # 写入日志文件
    if LOG_FILE:
        LOG_FILE.write(f"{formatted_message}\n")
        LOG_FILE.flush()  # 立即写入文件

    print(formatted_message)


def main():
    log("开始删除无效种子")
    # 定义 API URL
    FETCH_API_URL = f"{QB_ADDRESS}/api/v2/torrents/info"
    TRACKERS_API_URL = f"{QB_ADDRESS}/api/v2/torrents/trackers"
    DELETE_API_URL = f"{QB_ADDRESS}/api/v2/torrents/delete"

    # 从 API 获取种子信息
    try:
        response = requests.get(FETCH_API_URL)
        response.raise_for_status()
    except requests.exceptions.RequestException:
        log("无法连接到种子下载器")

    # 解析并过滤 JSON 响应
    torrents_data = response.json()

    # 提取匹配的种子哈希值和名称
    torrents = [(t.get("hash"), t.get("name")) for t in torrents_data]

    # 初始化数组以存储要删除的种子
    torrents_to_delete = []

    # 检查每个种子的 tracker 是否有特定消息
    for hash_val, name in torrents:
        try:
            trackers_response = requests.get(f"{TRACKERS_API_URL}?hash={hash_val}")
            trackers_response.raise_for_status()
            trackers_data = trackers_response.json()

            # 检查是否有任何 tracker 有"torrent not registered with this tracker"消息
            if any(
                tracker.get("msg") == "torrent not registered with this tracker"
                for tracker in trackers_data
            ):
                torrents_to_delete.append((hash_val, name))
        except requests.exceptions.RequestException:
            log(f"无法获取种子 {name} 的 tracker 信息")
            continue

    # 遍历每个要删除的种子
    for hash_val, name in torrents_to_delete:
        # 发送 POST 请求删除种子
        delete_data = {"hashes": hash_val, "deleteFiles": "true"}

        try:
            delete_response = requests.post(DELETE_API_URL, data=delete_data)
            delete_response.raise_for_status()

            # 输出删除信息
            log(f"已删除无效种子: {name}")
        except requests.exceptions.RequestException:
            continue


if __name__ == "__main__":
    main()
