#!/bin/bash

create_swapfile() {
    # 获取第一个参数
    swap_size=$1
    swap_file="/swapfile"

    if [ -f "$swap_file" ]; then
        echo "交换文件已存在"
        return 1
    fi

    echo "创建大小为 ${swap_size}MB 的交换文件..."
    dd if=/dev/zero of=/swapfile bs=1M count="${swap_size}"
    sudo chmod 600 "$swap_file"
    sudo mkswap "$swap_file"

    echo "交换文件创建完成。"
}

enable_swap() {
    swap_file="/swapfile"

    echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null

    sudo swapon "$swap_file"
    echo "交换文件已启用。"
}

# 检查参数
if [ $# -ne 1 ]; then
    echo "用法: $0 <swap_size_in_MB>"
    exit 1
fi
# 调用函数
create_swapfile "$1"
if [ $? -eq 0 ]; then
    enable_swap
else
    echo "交换文件创建失败。"
    exit 1
fi
