import os
import time
import requests

QB_ADDRESS = "http://192.168.2.10:8079"


def log(message):
    """日志记录函数"""
    # 获取环境变量
    log_folder = os.getenv("LOG_FOLDER")

    message = f"{time.ctime()}: {message}"

    if isinstance(log_folder, str) and os.path.exists(log_folder):
        # 确保日志文件夹存在
        os.makedirs(os.path.join(log_folder, "qB"), exist_ok=True)

        # 记录日志
        with open(
            os.path.join(log_folder, "qB", "unselectFile.txt"), "w", encoding="utf-8"
        ) as log_file:
            log_file.write(f"{time.ctime()}: {message}\n")


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

        # 遍历文件列表，找到大小小于50MB的文件
        for file in files:
            if file["size"] < 50 * 1024 * 1024 and file["priority"] != 0:
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
