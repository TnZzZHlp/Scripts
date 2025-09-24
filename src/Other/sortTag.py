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

    def get_group_letter(tag_line):
        """
        只按A-Z分组，支持中文拼音首字母、日文假名罗马音首字母，其他全部归为#组。
        """
        import jaconv

        cleaned_tag_content = tag_line.lstrip("#").strip()
        if not cleaned_tag_content:
            return "#"
        first_char = cleaned_tag_content[0]
        letter = "#"
        if "\u4e00" <= first_char <= "\u9fff":
            # 特殊多音字优先
            special_chars = {
                "长": "c",  # 长沙的长读作cháng
            }
            if first_char in special_chars:
                letter = special_chars[first_char].upper()
            else:
                from pypinyin import pinyin, Style

                py = pinyin(first_char, style=Style.NORMAL, errors="default")[0][0]
                letter = py[0].upper() if py else "#"
        elif ("\u3040" <= first_char <= "\u309f") or (
            "\u30a0" <= first_char <= "\u30ff"
        ):
            # 日文假名，先转平假名再转罗马音
            hira = jaconv.kata2hira(first_char)
            roma = jaconv.kana2alphabet(hira)
            if not roma:
                # 如果平假名转换失败，直接尝试原字符
                roma = jaconv.kana2alphabet(first_char)
            if roma:
                letter = roma[0].upper()
            else:
                letter = "#"
        else:
            letter = first_char.upper() if first_char.isalpha() else "#"
        if letter >= "A" and letter <= "Z":
            return letter
        else:
            return "#"

    # 先分组收集标签
    from collections import defaultdict

    group_dict = defaultdict(list)
    for tag in sorted_tags:
        group_letter = get_group_letter(tag)
        group_dict[group_letter].append(tag)

    # 按A-Z顺序输出，最后输出#组
    import string

    first_group = True
    for group_letter in list(string.ascii_uppercase) + ["#"]:
        tag_list = group_dict.get(group_letter, [])
        if not tag_list:
            continue
        if not first_group:
            print("")
        print(group_letter)
        for i in range(0, len(tag_list), 3):
            print(" | ".join(tag_list[i : i + 3]))
        first_group = False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="按字母顺序（中文按拼音）对文本文件中的标签进行排序。"
    )
    parser.add_argument("file_path", help="包含标签的 .txt 文件的路径，每行一个标签。")
    args = parser.parse_args()

    sort_tags_from_file(args.file_path)
