import os
import time
import requests

QB_ADDRESS = "http://192.168.2.10:8079"
RULES = [
    {"keyword": "hhd800.com@", "replace": ""},
    {"keyword": "_", "replace": "-"},
]

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

            log_path = os.path.join(log_folder, "qB", "autoRename.txt")
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
        for rule in RULES:
            # 获取文件名
            files = requests.get(
                f"{QB_ADDRESS}/api/v2/torrents/files?hash={torrent['hash']}"
            ).json()

            for file in files:
                # 获取文件名
                file_name = file["name"]

                if rule["keyword"] in file_name and file["priority"] != 0:
                    # 获取hash
                    hash = torrent["hash"]

                    old_path = file["name"]
                    new_path = old_path.replace(rule["keyword"], rule["replace"])

                    # 重命名文件
                    resp = requests.post(
                        f"{QB_ADDRESS}/api/v2/torrents/renameFile",
                        data={
                            "hash": hash,
                            "oldPath": old_path,
                            "newPath": new_path,
                        },
                    )

                    if resp.status_code == 200:
                        log(f"命名文件: {old_path} -> {new_path}")

                    else:
                        # 重命名失败
                        log(
                            f"重命名文件失败: {old_path} -> {new_path}, {resp.status_code}\n"
                        )


if __name__ == "__main__":
    main()
