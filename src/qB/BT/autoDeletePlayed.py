import os
import time
import requests

QB_ADDRESS = "http://192.168.2.10:8079"
QB_CATEGORY = "H"
JELLYFIN_ADDRESS = "http://192.168.2.10:8096"
JELLYFIN_USER_ID = "31b12ed73a1947249b03c69b43c51955"
JELLYFIN_API_KEY = "13061956301348ec9339509b67064280"
JELLYFIN_LIB_ID = "44a4bfe98a84d56a95021c889e6bb653"

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

            log_path = os.path.join(log_folder, "qB", "autoDeletePlayed.txt")
            LOG_FILE = open(log_path, "a", encoding="utf-8")

    timestamp = time.ctime()
    formatted_message = f"{timestamp}: {message}"

    # 写入日志文件
    if LOG_FILE:
        LOG_FILE.write(f"{formatted_message}\n")
        LOG_FILE.flush()  # 立即写入文件

    print(formatted_message)


def main():
    try:
        # 获取 Jellfin 库里所有的项目
        response = requests.get(
            f"{JELLYFIN_ADDRESS}/Items?",
            params={
                "userId": JELLYFIN_USER_ID,
                "parentId": JELLYFIN_LIB_ID,
                "isFavorite": False,
                "isPlayed": True,
            },
            headers={"Authorization": f"MediaBrowser Token={JELLYFIN_API_KEY}"},
        )
        response.raise_for_status()
        json_data = response.json()
        items = [item["Name"].replace("FC2-PPV", "FC2") for item in json_data["Items"]]

        log(f"获取到 {len(items)} 个已播放视频")

        # 获取 qBittorrent 中的所有种子
        response = requests.get(
            f"{QB_ADDRESS}/api/v2/torrents/info", params={"category": QB_CATEGORY}
        )
        response.raise_for_status()
        torrents = response.json()
        log(f"获取到 {len(torrents)} 个种子")

        for torrent in torrents:
            # 检查种子名是否与任何已播放视频匹配
            torrent_name = torrent["name"].replace("FC2-PPV", "FC2")
            for item in items:
                # 如果种子名包含在视频名中，或视频名包含在种子名中
                if torrent_name in item or item in torrent_name:
                    log(f"删除种子: {torrent['name']}")
                    response = requests.post(
                        f"{QB_ADDRESS}/api/v2/torrents/delete",
                        data={"hashes": torrent["hash"], "deleteFiles": True},
                    )

                    response.raise_for_status()
                    log(f"删除成功: {torrent['name']}")

    except Exception as e:
        log(f"删除过程出现错误: {e}")
        return


if __name__ == "__main__":
    main()
