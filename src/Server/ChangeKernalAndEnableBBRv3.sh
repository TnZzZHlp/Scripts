# 创建并写入 DEB822 格式的源文件
echo "Types: deb
URIs: https://deb.xanmod.org
Suites: $(lsb_release -sc)
Components: main
Signed-By: /etc/apt/keyrings/xanmod-archive-keyring.gpg" | sudo tee /etc/apt/sources.list.d/xanmod.sources > /dev/null

sudo apt update -y
sudo apt install linux-xanmod-x64v3 -y

echo "
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
net.core.default_qdisc = fq_pie
net.ipv4.tcp_congestion_control = bbr
net.ipv4.tcp_rmem = 4096 87380 33554432
net.ipv4.tcp_wmem = 4096 87380 33554432
" | tee /etc/sysctl.d/99-sysctl.conf > /dev/null

# 应用配置
sysctl --system