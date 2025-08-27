#!/bin/bash

# GitHub CLI 安装脚本
# 此脚本会自动安装 GitHub CLI (gh) 工具

echo "开始安装 GitHub CLI..."

# 检查并安装 curl（如果需要）
(type -p curl >/dev/null || (sudo apt update && sudo apt install curl -y)) \
	&& sudo mkdir -p -m 755 /etc/apt/keyrings \
	&& curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
	&& sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
	&& sudo mkdir -p -m 755 /etc/apt/sources.list.d \
	&& sudo tee /etc/apt/sources.list.d/github-cli.sources > /dev/null <<EOF
Types: deb
URIs: https://cli.github.com/packages
Suites: stable
Components: main
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/githubcli-archive-keyring.gpg
EOF \
	&& sudo apt update \
	&& sudo apt install gh -y

# 检查安装是否成功
if command -v gh &> /dev/null; then
    echo "GitHub CLI 安装成功！"
    echo "版本信息："
    gh --version
    echo ""
    echo "使用 'gh auth login' 来登录您的 GitHub 账户"
else
    echo "GitHub CLI 安装失败，请检查错误信息"
    exit 1
fi