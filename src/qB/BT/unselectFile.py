import os
import time
import requests

QB_ADDRESS = "http://192.168.255.77:8080"

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

            log_path = os.path.join(log_folder, "qB", "unselectFile.txt")
            LOG_FILE = open(log_path, "a", encoding="utf-8")

    timestamp = time.ctime()
    formatted_message = f"{timestamp}: {message}"

    # 写入日志文件
    if LOG_FILE:
        LOG_FILE.write(f"{formatted_message}\n")
        LOG_FILE.flush()  # 立即写入文件

    print(formatted_message)


def main():
    # 下载中的种子列表
    torrents = requests.get(
        f"{QB_ADDRESS}/api/v2/torrents/info?filter=downloading"
    ).json()

    for torrent in torrents:
        # 获取hash
        hash = torrent["hash"]

        # 获取文件列表
        files = requests.get(f"{QB_ADDRESS}/api/v2/torrents/files?hash={hash}").json()

        # 遍历文件列表，找到大小小于20MB的文件
        for file in files:
            if file["size"] < 20 * 1024 * 1024 and file["priority"] != 0:
                # 获取index
                index = file["index"]

                # 取消选择文件
                resp = requests.post(
                    f"{QB_ADDRESS}/api/v2/torrents/filePrio",
                    data={"hash": hash, "id": index, "priority": 0},
                )

                if resp.status_code == 200:
                    log(f"取消选择文件: {file['name']}")
                else:
                    log(f"取消选择文件失败: {file['name']}, {resp.status_code}\n")


if __name__ == "__main__":
    main()
