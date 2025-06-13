import argparse
import aiohttp
import asyncio
import logging
from tqdm.asyncio import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm
from aiohttp_socks import ProxyConnector

from tenacity import retry, stop_after_attempt

DOMAIN = None
SEM = asyncio.Semaphore(2)  # 限制并发下载数量
USERNAME = ""
PROXY = "socks5://192.168.2.1:7890"

# 在脚本开始处配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


async def parse_artist_url(url: str, session) -> list:
    """
    解析 Kemono Artist 的 URL，提取出 所有资源页面url。
    支持分页加载所有内容。
    """

    # 判断是否是 Kemono 还是 Coomer
    if "kemono" not in url and "coomer" not in url:
        raise ValueError("URL 必须是 Kemono 或 Coomer 的 Artist 页面。")

    # 分割URL后取后三部分
    global DOMAIN
    global USERNAME
    USERNAME = url.split("/")[-1]  # 获取用户名
    DOMAIN = url.split("/")[2]
    parts = "/".join(url.split("/")[-3:])

    # 初始化变量
    all_ids = []
    offset = 0
    page_size = 50  # API默认每页返回50条记录
    total_count = None

    # 循环获取所有页面的内容
    while True:
        if "kemono" in DOMAIN or "coomer" in DOMAIN:
            resource_url = f"https://{DOMAIN}/api/v1/{parts}/posts-legacy?o={offset}"
        else:
            raise ValueError("URL 必须是 Kemono 或 Coomer 的 Artist 页面。")

        logging.info(f"正在获取页面，偏移量: {offset}")
        response = await session.get(
            resource_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0"
            },
        )

        if response.status != 200:
            raise ValueError(f"无法访问 {resource_url} 或该页面不存在。")

        json_data = await response.json()

        # 获取总数，只在第一次请求时设置
        if (
            total_count is None
            and "props" in json_data
            and "count" in json_data["props"]
        ):
            total_count = json_data["props"]["count"]
            logging.info(f"共有 {total_count} 个资源需要获取")

        # 获取当前页的ID
        current_page_ids = [item["id"] for item in json_data["results"]]
        all_ids.extend(current_page_ids)

        # 如果这一页没有返回任何结果或者已经获取了所有内容，则退出循环
        if not current_page_ids or (
            total_count is not None and len(all_ids) >= total_count
        ):
            break

        # 增加偏移量，继续获取下一页
        offset += page_size

    logging.info(f"共获取到 {len(all_ids)} 个资源ID")

    # 获取所有资源的详细信息
    resource_details = []
    # 进度条
    pbar = tqdm(total=len(all_ids))
    for id in all_ids:
        await get_detail(id, parts, resource_details, session)
        pbar.set_description(f"正在获取 {id} 信息")
        pbar.update(1)
    pbar.close()
    return resource_details


@retry(stop=stop_after_attempt(3))
async def get_detail(id, parts, resource_details, session):
    async with session.get(
        f"https://{DOMAIN}/api/v1/{parts}/post/{id}",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0",
            "Accept": "*/*",
        },
    ) as response:
        if response.status == 200:
            data = await response.json()
            if "attachments" in data:
                resource_details.append(data["attachments"])


# 强制每次请求后关闭连接，避免 WinError 64
@retry(stop=stop_after_attempt(3), reraise=True)
async def download_file(result, output_folder: str, session):
    """
    下载视频并保存到指定文件夹，支持断点续传。
    """

    url = ""
    filename = ""

    # 获取限制
    async with SEM:
        try:
            for attachment in result:
                # 确保输出文件夹存在
                import os

                if not os.path.exists(f"{output_folder}/{USERNAME}"):
                    os.makedirs(f"{output_folder}/{USERNAME}")

                filename = attachment["name"]
                output_path = f"{output_folder}/{USERNAME}/{filename}"

                url = f"{attachment['server']}/data{attachment['path']}"

                # 检查文件是否已存在，计算已下载的大小
                downloaded_size = 0
                file_exists = os.path.exists(output_path)
                if file_exists:
                    downloaded_size = os.path.getsize(output_path)

                # 准备请求头，添加断点续传
                headers = {
                    "Accept": "*/*",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0",
                }

                # 如果已经下载了部分文件，添加Range头
                if downloaded_size > 0:
                    headers["Range"] = f"bytes={downloaded_size}-"

                async with session.get(
                    url,
                    headers=headers,
                ) as response:
                    if response.status == 416:  # 请求范围不满足
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
            logging.error(f"下载失败 Filename: {filename} URL: {url} - 错误: {e}")
            raise  # 重新抛出以触发 tenacity 重试


# 2. 创建异步主函数并修复任务调度
async def async_main(url, output_folder):
    # 使用长连接，并将最大并发数与 SEM 保持一致，设置 keepalive
    connector = ProxyConnector.from_url(
        PROXY, limit=SEM._value + 8, keepalive_timeout=30
    )
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=0, sock_read=300),
    ) as session:
        logging.info(f"正在解析 Kemono / Coomer Artist 的 URL: {url}")

        resources = await parse_artist_url(url, session)

        tasks = []
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

    asyncio.run(async_main(args.url, args.output))


if __name__ == "__main__":
    main()
