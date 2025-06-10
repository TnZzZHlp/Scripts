import argparse
import aiohttp
import requests
import asyncio
from aiohttp_socks import ProxyType, ProxyConnector, ChainProxyConnector

DOMAIN = None
SEM = asyncio.Semaphore(2)  # 限制并发下载数量
PROXY = "socks5://192.168.2.1:7890"


def parse_artist_url(url: str) -> list:
    """
    解析 Kemono Artist 的 URL，提取出 所有资源页面url。
    """

    # 判断是否是 Kemono 还是 Coomer
    if "kemono" not in url and "coomer" not in url:
        raise ValueError("URL 必须是 Kemono 或 Coomer 的 Artist 页面。")

    # 分割URL后取后三部分
    global DOMAIN
    DOMAIN = url.split("/")[2]
    parts = "/".join(url.split("/")[-3:])
    if "kemono" in DOMAIN:
        resource_url = f"https://{DOMAIN}/api/v1/{parts}/posts-legacy"
    elif "coomer" in DOMAIN:
        resource_url = f"https://{DOMAIN}/api/v1/{parts}/posts-legacy"
    else:
        raise ValueError("URL 必须是 Kemono 或 Coomer 的 Artist 页面。")

    response = requests.get(
        resource_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0"
        },
    )
    if response.status_code != 200:
        raise ValueError("无法访问该 URL 或该页面不存在。")

    json = response.json()

    return json["results"]


async def download_file(result, output_folder: str):
    """
    下载视频并保存到指定文件夹。
    """

    # 获取限制
    async with SEM:
        if "file" not in result or "path" not in result["file"]:
            raise ValueError("结果中没有找到视频文件信息。")

        # 确保输出文件夹存在
        import os

        if not os.path.exists(f"{output_folder}/videos/"):
            os.makedirs(f"{output_folder}/videos/")

        filename = result["file"]["name"]
        output_path = f"{output_folder}/videos/{filename}"

        # 判断输出文件夹是否已经有该文件
        if os.path.exists(output_path):
            print(f"视频已存在，跳过下载: {output_path}")
            return

        url = f"https://{DOMAIN}{result['file']['path']}"

        try:
            async with aiohttp.ClientSession(
                connector=ProxyConnector.from_url(PROXY)
            ) as session:
                async with session.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0"
                    },
                ) as response:
                    print(f"正在下载视频: {url}")
                    if response.status != 200:
                        raise ValueError(f"无法下载视频。{response.status}")

                    with open(output_path, "wb") as file:
                        # 每次读取1MB
                        chunk_size = 1024 * 1024
                        while True:
                            chunk = await response.content.read(chunk_size)
                            if not chunk:
                                break
                            file.write(chunk)

                    print(f"视频已保存到: {output_path}")
        except Exception as e:
            print(f"下载视频时出错: {e}")


async def download_attachments(result, output_folder: str):
    """
    下载附件并保存到指定文件夹。
    """

    # 获取限制
    async with SEM:
        if "attachments" not in result:
            print("没有找到附件信息。")
            return

        for attachment in result["attachments"]:
            if "file" not in attachment or "path" not in attachment["file"]:
                print("附件信息不完整，跳过。")
                continue

            # 确保附件输出文件夹存在
            attachments_folder = f"{output_folder}/attachments"
            import os

            if not os.path.exists(attachments_folder):
                os.makedirs(attachments_folder)
            filename = attachment["file"]["name"]
            output_path = f"{attachments_folder}/{filename}"

            # 判断输出文件夹是否已经有该文件
            if os.path.exists(output_path):
                print(f"附件已存在，跳过下载: {output_path}")
                continue

            url = f"https://{DOMAIN}{attachment['file']['path']}"

            try:
                async with aiohttp.ClientSession(
                    connector=ProxyConnector.from_url(PROXY)
                ) as session:
                    async with session.get(
                        url,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0"
                        },
                    ) as response:
                        print(f"正在下载附件: {url}")
                        if response.status != 200:
                            print(f"无法下载附件: {url} {response.status}")
                            continue

                        with open(output_path, "wb") as file:
                            # 每次读取1MB
                            chunk_size = 1024 * 1024
                            while True:
                                chunk = await response.content.read(chunk_size)
                                if not chunk:
                                    break
                                file.write(chunk)

                        print(f"附件已保存到: {output_path}")
            except Exception as e:
                print(f"下载附件时出错: {e}")


# 2. 创建异步主函数并修复任务调度
async def async_main(resources, output_folder):
    tasks = []
    for resource in resources:
        tasks.append(asyncio.create_task(download_file(resource, output_folder)))
        tasks.append(asyncio.create_task(download_attachments(resource, output_folder)))

    if tasks:
        await asyncio.gather(*tasks)


def main():
    parser = argparse.ArgumentParser(
        description="下载 Kemono / Coomer 的视频并保存到文件夹"
    )
    parser.add_argument("url", help="Kemono / Coomer Artist 的 URL")
    parser.add_argument(
        "--output",
        "-o",
        default="./download",
        help="保存下载视频的文件夹，默认为当前目录",
    )
    args = parser.parse_args()

    print(f"正在解析 Kemono / Coomer Artist 的 URL: {args.url}")

    resources = []
    try:
        resources = parse_artist_url(args.url)
    except Exception as e:
        print(f"解析失败: {e}")

    if resources:
        asyncio.run(async_main(resources, args.output))
    else:
        print("没有找到任何资源")


if __name__ == "__main__":
    main()
