# 检查是否 root
if [ "$EUID" -ne 0 ]; then
    echo "请以 root 用户身份运行此脚本。"
    exit 1
fi

# 下载密钥
echo "正在下载 XanMod GPG 密钥..."
mkdir -p /etc/apt/keyrings
curl -fsSL https://dl.xanmod.org/archive.key | gpg --dearmor -o /etc/apt/keyrings/xanmod-archive-keyring.gpg


# 创建并写入 DEB822 格式的源文件
echo "正在创建源列表文件..."
echo "Types: deb
URIs: https://deb.xanmod.org
Suites: $(lsb_release -sc)
Components: main
Signed-By: /etc/apt/keyrings/xanmod-archive-keyring.gpg" | tee /etc/apt/sources.list.d/xanmod.sources > /dev/null

# 更新软件包列表并安装内核
echo "正在更新软件包列表并安装内核..."
apt update -y
apt install linux-xanmod-x64v3 -y

# 设置 sysctl 参数
echo "正在设置 sysctl 参数..."
echo "
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
net.core.default_qdisc = fq_pie
net.ipv4.tcp_congestion_control = bbr
net.ipv4.tcp_rmem = 4096 87380 33554432
net.ipv4.tcp_wmem = 4096 87380 33554432
" | tee /etc/sysctl.d/99-sysctl.conf > /dev/null

# 应用配置
if sysctl --system; then
    echo "sysctl 配置应用成功。"
else
    echo "sysctl 配置应用失败。"
fi