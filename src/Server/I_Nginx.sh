#!/bin/bash

echo "正在安装 Node Exporter..."

# 检查是否以 root 用户运行脚本
if [ "$(id -u)" -ne 0 ]; then
    echo "请使用 root 用户运行此脚本。"
    exit 1
fi

# 安装必备依赖
echo "正在安装必备依赖..."
apt install curl gnupg2 ca-certificates lsb-release debian-archive-keyring

# 下载并添加 GPG 密钥
echo "正在下载并添加 GPG 密钥..."
mkdir -p /usr/share/keyrings
curl https://nginx.org/keys/nginx_signing.key | gpg --dearmor \
    | sudo tee /usr/share/keyrings/nginx-archive-keyring.gpg >/dev/null

# 创建并写入 DEB822 格式的 Nginx 源文件
echo "正在创建 Nginx 源文件..."
sudo tee /etc/apt/sources.list.d/nginx.sources > /dev/null <<EOF
Types: deb
URIs: https://nginx.org/packages/debian
Suites: $(lsb_release -sc)
Components: nginx
Signed-By: /usr/share/keyrings/nginx-archive-keyring.gpg
EOF

# 更新软件包列表
echo "正在更新软件包列表..."
apt update

# 安装 Nginx
echo "正在安装 Nginx..."
apt install nginx
