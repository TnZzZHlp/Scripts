#!/bin/bash

echo "正在安装 Prometheus..."

# 检查是否以 root 用户运行脚本
if [ "$(id -u)" -ne 0 ]; then
    echo "请使用 root 用户运行此脚本。"
    exit 1
fi

apt update -y && apt install -y curl jq tar

# 获取 Prometheus 最新版本下载链接
echo "正在获取 Prometheus 最新版本下载链接..."
DOWNLOAD_LINK=$(curl -s https://api.github.com/repos/prometheus/prometheus/releases/latest | jq -r '.assets[] | select(.name | contains("linux-amd64")) | .browser_download_url')

# 检查是否成功获取下载链接
if [ -z "$DOWNLOAD_LINK" ]; then
    echo "无法获取 Prometheus 下载链接，请检查网络连接或 GitHub API 状态。"
    exit 1
fi

# 下载 Prometheus
echo "正在下载 Prometheus..."
cd /tmp && curl -LO "$DOWNLOAD_LINK"

# 检查下载是否成功
if [ $? -ne 0 ]; then
    echo "下载 Prometheus 失败，请检查网络连接。"
    exit 1
fi

# 解压 Prometheus
tar -xzf prometheus-*.tar.gz

# 移动 Prometheus 到 /usr/local/bin
sudo mv prometheus-*/prometheus /usr/local/bin/
mkdir -p /etc/prometheus
sudo mv prometheus-*/prometheus.yml /etc/prometheus/

cat <<EOF | sudo tee /etc/systemd/system/prometheus.service >/dev/null
[Unit]
Description=Prometheus
After=network.target

[Service]
User=root
ExecStart=/usr/local/bin/prometheus --config.file=/etc/prometheus/prometheus.yml

[Install]
WantedBy=multi-user.target
EOF

# 重新加载 systemd 配置并启动、开机自启
sudo systemctl daemon-reload
sudo systemctl start prometheus
sudo systemctl enable prometheus

echo "Prometheus 安装完成！"
