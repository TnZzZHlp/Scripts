import argparse
import os
import logging


def remove_same_name(directory, recursive=False, dry_run=False):
    seen = {}

    def process_file(root, filename):
        base, _ = os.path.splitext(filename)
        key = base.lower()
        path = os.path.join(root, filename)
        if key in seen:
            logging.info(f"删除重复文件: {path}")
            if not dry_run:
                os.remove(path)
        else:
            seen[key] = path

    if recursive:
        for root, _, files in os.walk(directory):
            for fname in files:
                process_file(root, fname)
    else:
        for fname in os.listdir(directory):
            path = os.path.join(directory, fname)
            if os.path.isfile(path):
                process_file(directory, fname)


def main():
    parser = argparse.ArgumentParser(
        description="删除目录下同名文件（忽略后缀），只保留第一个出现的"
    )
    parser.add_argument("directory", help="目标目录路径")
    parser.add_argument("-r", "--recursive", action="store_true", help="递归处理子目录")
    parser.add_argument(
        "--dry-run", action="store_true", help="仅打印将删除的文件，不执行删除"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    if not os.path.isdir(args.directory):
        logging.error(f"目录不存在: {args.directory}")
        return

    remove_same_name(args.directory, args.recursive, args.dry_run)


if __name__ == "__main__":
    main()
