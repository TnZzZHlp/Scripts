#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pypinyin import pinyin, Style


def get_sort_key(tag_line):
    """
    生成用于排序的键。
    对于中文，提取每个字拼音的首字母进行排序。
    对于英文和数字，转换为小写。
    标签前面的'#'和两端的空格会被移除后再处理。
    """
    # 移除标签行首的 '#' 和两端的空格，得到纯标签内容
    cleaned_tag_content = tag_line.lstrip("#").strip()

    if not cleaned_tag_content:
        return ""  # 空标签的排序键

    # 特殊字符的拼音首字母映射（如果需要）
    special_chars = {
        "长": "c",  # 长沙的长读作cháng
    }

    # 获取每个字符的拼音首字母
    result = []
    for char in cleaned_tag_content:
        if "\u4e00" <= char <= "\u9fff":  # 中文字符
            if char in special_chars:
                result.append(special_chars[char])
            else:
                # 先获取完整拼音，然后取首字母
                char_pinyin_full = pinyin(char, style=Style.TONE3, errors="default")[0][
                    0
                ]
                # 移除声调数字，取首字母
                clean_pinyin = "".join(c for c in char_pinyin_full if not c.isdigit())
                if clean_pinyin:
                    result.append(clean_pinyin[0].lower())
        else:
            # 非中文字符直接添加并转换为小写
            result.append(char.lower())

    sort_key_string = "".join(result)

    return sort_key_string


def sort_tags_from_file(file_path):
    """
    从文件中读取标签，排序后打印。
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # 读取每一行，去除首尾空格，并过滤掉空行
            # 保留原始行（包括#号和可能的内部空格）用于最终输出
            tags = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"错误：文件未找到 {file_path}")
        return
    except Exception as e:
        print(f"读取文件时出错: {e}")
        return

    if not tags:
        print("文件中没有找到标签。")
        return

    # 排序
    sorted_tags = sorted(tags, key=get_sort_key)

    print("排序后的标签：")
    for tag in sorted_tags:
        print(tag)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="按字母顺序（中文按拼音）对文本文件中的标签进行排序。"
    )
    parser.add_argument("file_path", help="包含标签的 .txt 文件的路径，每行一个标签。")
    args = parser.parse_args()

    sort_tags_from_file(args.file_path)
