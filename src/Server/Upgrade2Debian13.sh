#!/bin/bash

# 更新 Debian 13 的软件源
update_sources() {
    echo "正在更新 Debian 13 的软件源..."
    echo 'Types: deb
URIs: https://deb.debian.org/debian
Suites: trixie trixie-updates trixie-backports
Components: main contrib non-free non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

# 默认注释了源码镜像以提高 apt update 速度，如有需要可自行取消注释
# Types: deb-src
# URIs: https://deb.debian.org/debian
# Suites: bookworm bookworm-updates bookworm-backports
# Components: main contrib non-free non-free-firmware
# Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

# 以下安全更新软件源包含了官方源与镜像站配置，如有需要可自行修改注释切换
Types: deb
URIs: https://deb.debian.org/debian-security
Suites: trixie-security
Components: main contrib non-free non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

# # Types: deb-src
# # URIs: https://deb.debian.org/debian-security
# # Suites: trixie-security
# # Components: main contrib non-free non-free-firmware
# # Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: https://deb.debian.org/debian
Suites: trixie-backports
Components: main contrib non-free non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

# Types: deb-src
# URIs: https://deb.debian.org/debian
# Suites: trixie-backports
# Components: main contrib non-free non-free-firmware
# Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: https://deb.debian.org/debian
Suites: trixie-updates
Components: main contrib non-free non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

# Types: deb-src
# URIs: https://deb.debian.org/debian
# Suites: trixie-updates
# Components: main contrib non-free non-free-firmware
# Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

' | sudo tee /etc/apt/sources.list.d/debian.sources

    if [ $? -ne 0 ]; then
        echo "更新软件源失败，请检查权限或网络连接。"
        exit 1
    fi

    # 备份原有 sources.list 文件
    if [ -f /etc/apt/sources.list ]; then
        echo "备份原有 sources.list 文件..."
        mv /etc/apt/sources.list /etc/apt/sources.list.bak
    fi

    echo "Debian 13 的软件源更新完成！"
}

upgrade_system() {
    echo "正在升级系统..."
    apt update
    apt upgrade -y
    apt full-upgrade -y
    apt autoclean
    apt autoremove -y
    echo "系统升级完成！"
}

upgrade_system
update_sources
upgrade_system
