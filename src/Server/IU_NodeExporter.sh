#! /bin/bash

echo "正在安装 Node Exporter..."

# 检查是否以 root 用户运行脚本
if [ "$(id -u)" -ne 0 ]; then
    echo "请使用 root 用户运行此脚本。"
    exit 1
fi

apt update -y && apt install -y curl jq tar

# 获取 Node Exporter 最新版本下载链接
echo "正在获取 Node Exporter 最新版本下载链接..."
DOWNLOAD_LINK=$(curl -s https://api.github.com/repos/prometheus/node_exporter/releases/latest | jq -r '.assets[] | select(.name | contains("linux-amd64")) | .browser_download_url')

# 检查是否成功获取下载链接
if [ -z "$DOWNLOAD_LINK" ]; then
    echo "无法获取 Node Exporter 下载链接，请检查网络连接或 GitHub API 状态。"
    exit 1
fi

# 下载 Node Exporter
echo "正在下载 Node Exporter..."
cd /tmp && curl -LO "$DOWNLOAD_LINK"

# 检查下载是否成功
if [ $? -ne 0 ]; then
    echo "下载 Node Exporter 失败，请检查网络连接。"
    exit 1
fi

# 解压 Node Exporter
tar -xzf node_exporter-*.tar.gz

# 移动 Node Exporter 到 /usr/local/bin
sudo mv node_exporter-*/node_exporter /usr/local/bin/

cat <<EOF | sudo tee /etc/systemd/system/node_exporter.service >/dev/null
[Unit]
Description=Node Exporter
After=network.target

[Service]
User=root
ExecStart=/usr/local/bin/node_exporter

[Install]
WantedBy=multi-user.target
EOF

# 重新加载 systemd 配置并启动、开机自启
sudo systemctl daemon-reload
sudo systemctl start node_exporter
sudo systemctl enable node_exporter

echo "Node Exporter 安装完成！"
