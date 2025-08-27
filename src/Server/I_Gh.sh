#!/bin/bash

# GitHub CLI 安装脚本
# 此脚本会自动安装 GitHub CLI (gh) 工具

set -euo pipefail  # 启用严格模式：遇到错误立即退出，未定义变量报错，管道错误传播

echo "开始安装 GitHub CLI..."

# 检查是否为root用户或有sudo权限
if [[ $EUID -eq 0 ]]; then
    SUDO=""
else
    if ! command -v sudo &> /dev/null; then
        echo "错误：需要sudo权限来安装软件包，但系统中未找到sudo命令"
        exit 1
    fi
    SUDO="sudo"
fi

# 检查系统是否为Debian/Ubuntu
if ! command -v dpkg &> /dev/null; then
    echo "错误：此脚本仅适用于基于Debian的系统（Debian/Ubuntu）"
    exit 1
fi

echo "正在检查并安装curl..."
# 检查并安装 curl（如果需要）
if ! command -v curl &> /dev/null; then
    echo "curl未安装，正在安装..."
    if ! $SUDO apt update; then
        echo "错误：无法更新软件包列表"
        exit 1
    fi
    if ! $SUDO apt install curl -y; then
        echo "错误：无法安装curl"
        exit 1
    fi
fi

# 检查网络连接
echo "正在检查网络连接..."
if ! curl -s --connect-timeout 5 https://cli.github.com &> /dev/null; then
    echo "错误：无法连接到GitHub CLI服务器，请检查网络连接"
    exit 1
fi

echo "正在设置GPG密钥..."
# 创建密钥目录
if ! $SUDO mkdir -p -m 755 /etc/apt/keyrings; then
    echo "错误：无法创建密钥目录"
    exit 1
fi

# 下载并安装GPG密钥
if ! curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | $SUDO tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null; then
    echo "错误：无法下载或安装GPG密钥"
    exit 1
fi

# 设置密钥权限
if ! $SUDO chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg; then
    echo "错误：无法设置GPG密钥权限"
    exit 1
fi

echo "正在配置软件源..."
# 创建源列表目录
if ! $SUDO mkdir -p -m 755 /etc/apt/sources.list.d; then
    echo "错误：无法创建源列表目录"
    exit 1
fi

# 获取系统架构
ARCH=$(dpkg --print-architecture)
if [[ -z "$ARCH" ]]; then
    echo "错误：无法获取系统架构"
    exit 1
fi

# 创建软件源配置文件（deb822格式）
$SUDO tee /etc/apt/sources.list.d/github-cli.sources > /dev/null <<EOF
Types: deb
URIs: https://cli.github.com/packages
Suites: stable
Components: main
Architectures: $ARCH
Signed-By: /etc/apt/keyrings/githubcli-archive-keyring.gpg
EOF

if [[ $? -ne 0 ]]; then
    echo "错误：无法创建软件源配置文件"
    exit 1
fi

echo "正在更新软件包列表..."
# 更新软件包列表
if ! $SUDO apt update; then
    echo "错误：无法更新软件包列表"
    exit 1
fi

echo "正在安装GitHub CLI..."
# 安装GitHub CLI
if ! $SUDO apt install gh -y; then
    echo "错误：无法安装GitHub CLI"
    exit 1
fi

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