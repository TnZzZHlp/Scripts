"""
用于移动大文件的脚本：
1. 递归查找指定目录下所有文件
2. 按文件大小降序排序
3. 将大文件优先移动到ny文件夹，直到总大小达到24.5GB
4. 将剩余文件移动到nb文件夹
"""

import os
import shutil
import argparse

# 定义ny文件夹的大小上限为24.5GB（转换为字节）
NY_SIZE_LIMIT_GB = 24.5
NY_SIZE_LIMIT_BYTES = NY_SIZE_LIMIT_GB * 1024 * 1024 * 1024


def get_all_files_sorted_by_size(source_dir):
    """
    递归获取目录下所有文件并按大小降序排序
    参数:
    source_dir - 要扫描的源目录
    target_dir - 要排除的目标目录(如果在源目录内)

    返回: [(文件路径, 文件大小)] 按大小降序排序
    """
    all_files = []

    print(f"正在扫描目录: {source_dir}")

    for root, _, filenames in os.walk(source_dir):

        for filename in filenames:
            filepath = os.path.join(root, filename)
            try:
                file_size = os.path.getsize(filepath)
                all_files.append((filepath, file_size))
            except OSError as e:
                print(f"获取文件大小出错 {filepath}: {e}")

    # 按文件大小降序排序
    all_files.sort(key=lambda x: x[1], reverse=True)
    print(f"找到 {len(all_files)} 个文件")
    return all_files


def move_files_to_folders(source_dir):
    """
    将源目录中的文件移动到目标目录下的ny和nb文件夹中
    ny文件夹大小上限为24.5GB
    """
    # 确保目标目录及其子目录存在
    ny_folder = os.path.join(source_dir, "ny")
    nb_folder = os.path.join(source_dir, "nb")

    try:
        os.makedirs(ny_folder, exist_ok=True)
        os.makedirs(nb_folder, exist_ok=True)
        print(f"已创建目标文件夹: {ny_folder} 和 {nb_folder}")
    except OSError as e:
        print(f"创建目标文件夹出错: {e}")
        return

    # 获取所有文件并按大小排序
    sorted_files = get_all_files_sorted_by_size(source_dir)

    if not sorted_files:
        print("没有找到需要移动的文件")
        return

    # 开始移动文件
    ny_current_size = 0
    moved_count = 0

    for filepath, filesize in sorted_files:
        filename = os.path.basename(filepath)
        # 确定目标文件夹
        if ny_current_size + filesize <= NY_SIZE_LIMIT_BYTES:
            dest_folder = ny_folder
            ny_current_size += filesize
        else:
            dest_folder = nb_folder

        dest_path = os.path.join(dest_folder, filename)

        if dest_path == filepath:
            continue

        # 移动文件
        try:
            shutil.move(filepath, dest_path)
            moved_count += 1
            print(f"已移动 {moved_count} 个文件, 总文件数目: {len(sorted_files)}, ")

        except Exception as e:
            print(f"移动文件失败 {filepath}: {e}")

    # 打印最终统计信息
    print(f"\n文件移动完成!")
    print(f"总共移动了 {moved_count} 个文件")
    print(f"文件已成功分配到 {ny_folder} 和 {nb_folder}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将文件按大小分配到不同文件夹")
    parser.add_argument("source_dir", help="源目录(包含要移动的文件)")

    args = parser.parse_args()

    # 验证源目录存在
    if not os.path.isdir(args.source_dir):
        print(f"错误: 源目录 '{args.source_dir}' 不存在")
    else:
        move_files_to_folders(
            args.source_dir,
        )
