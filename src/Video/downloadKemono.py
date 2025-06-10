import argparse
from math import log
import aiohttp
import requests
from aiohttp_socks import ProxyConnector
import asyncio
import logging
from tqdm.asyncio import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from tenacity import retry, stop_after_attempt

DOMAIN = None
SEM = asyncio.Semaphore(2)  # 限制并发下载数量
PROXY = "socks5://192.168.2.1:7890"


# 在脚本开始处配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


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

    # 获取 Set-Cookie
    global COOKIES
    COOKIES = dict(response.cookies)

    json = response.json()

    # 拿到所有的id
    ids = [item["id"] for item in json["results"]]

    # 获取所有资源的详细信息
    resource_details = []
    # 进度条
    pbar = tqdm(total=len(ids))
    for id in ids:
        logging.info(f"正在获取资源 ID: {id}")
        get_detail(id, parts, resource_details)
        pbar.set_description(f"正在获取 {id} 信息")
        pbar.update(1)
    pbar.close()
    return resource_details


@retry(stop=stop_after_attempt(3))
def get_detail(id, parts, resource_details):
    response = requests.get(
        f"https://{DOMAIN}/api/v1/{parts}/post/{id}",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0",
            "Accept": "*/*",
        },
    )
    if response.status_code == 200:
        if "attachments" in response.json():
            resource_details.append(response.json()["attachments"])


@retry(stop=stop_after_attempt(3))
async def download_file(result, output_folder: str, session):
    """
    下载视频并保存到指定文件夹，支持断点续传。
    """

    url = ""

    # 获取限制
    async with SEM:
        try:
            for attachment in result:
                # 确保输出文件夹存在
                import os

                if not os.path.exists(f"{output_folder}"):
                    os.makedirs(f"{output_folder}")

                filename = attachment["name"]
                output_path = f"{output_folder}/{filename}"

                url = f"{attachment['server']}/data{attachment['path']}"
                logging.info(f"资源文件将保存到: {output_path}")

                # 检查文件是否已存在，计算已下载的大小
                downloaded_size = 0
                file_exists = os.path.exists(output_path)
                if file_exists:
                    downloaded_size = os.path.getsize(output_path)
                    logging.info(
                        f"找到已下载文件: {output_path}，已下载 {downloaded_size} 字节"
                    )

                # 准备请求头，添加Range以实现断点续传
                headers = {
                    "Accept": "*/*",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0",
                }

                # 如果已经下载了部分文件，添加Range头
                if downloaded_size > 0:
                    headers["Range"] = f"bytes={downloaded_size}-"
                    logging.info(f"从字节 {downloaded_size} 继续下载: {url}")

                async with session.get(
                    url,
                    headers=headers,
                ) as response:
                    if response.status == 416:  # 请求范围不满足
                        logging.info(f"文件已经完整下载: {output_path}")
                        return
                    elif response.status not in [200, 206]:  # 206是部分内容的状态码
                        raise ValueError(f"无法下载视频。状态码: {response.status}")

                    # 获取文件总大小
                    if response.status == 206:  # 部分内容
                        content_range = response.headers.get("Content-Range", "")
                        if content_range:
                            file_size = int(content_range.split("/")[-1])
                        else:
                            file_size = downloaded_size + response.content_length
                    else:  # 完整内容
                        file_size = response.content_length
                        downloaded_size = 0  # 重置已下载大小，因为这是一个全新的下载

                    # 检查文件是否已完整下载
                    if file_exists and downloaded_size == file_size:
                        logging.info(f"文件已存在且完整: {output_path}")
                        return

                    # 以追加模式打开文件进行断点续传
                    chunk_size = 4 * 1024 * 1024  # 4MB 是视频下载的良好平衡点

                    # 使用logging_redirect_tqdm确保日志和进度条不会冲突
                    with logging_redirect_tqdm():
                        # 显示总进度，包括已下载部分
                        progress = tqdm(
                            total=file_size,
                            initial=downloaded_size,
                            unit="B",
                            unit_scale=True,
                            desc=f"下载 {filename}",
                            ascii=True,
                        )
                        # 以追加模式打开文件
                        with open(
                            output_path, "ab" if downloaded_size > 0 else "wb"
                        ) as file:
                            async for chunk in response.content.iter_chunked(
                                chunk_size
                            ):
                                file.write(chunk)
                                progress.update(len(chunk))
                        progress.close()

                    # 检查下载是否完整
                    current_size = os.path.getsize(output_path)
                    if current_size != file_size:
                        logging.warning(
                            f"下载可能不完整: 当前大小 {current_size} != 预期大小 {file_size}"
                        )
                    else:
                        logging.info(f"视频已完整保存到: {output_path}")

        except Exception as e:
            logging.error(f"下载失败 URL: {url} - 错误: {e}")


# 2. 创建异步主函数并修复任务调度
async def async_main(resources, output_folder):
    tasks = []
    async with aiohttp.ClientSession(
        connector=ProxyConnector.from_url(PROXY),
        timeout=aiohttp.ClientTimeout(total=0, sock_read=30),
    ) as session:
        for resource in resources:
            tasks.append(
                asyncio.create_task(download_file(resource, output_folder, session))
            )
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

    logging.info(f"正在解析 Kemono / Coomer Artist 的 URL: {args.url}")

    resources = []
    try:
        resources = parse_artist_url(args.url)
    except Exception as e:
        logging.error(f"解析失败: {e}")

    if resources:
        asyncio.run(async_main(resources, args.output))
    else:
        logging.warning("没有找到任何资源")


if __name__ == "__main__":
    main()
