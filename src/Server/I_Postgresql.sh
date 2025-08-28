#!/bin/bash

# PostgreSQL 官方仓库安装脚本
# 支持 Debian/Ubuntu 系统
# 自动检测发行版并配置 PostgreSQL 官方 APT 仓库 (deb822 格式)

set -euo pipefail  # 严格模式：遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否为 root 用户或有 sudo 权限
check_privileges() {
    log_info "检查用户权限..."

    if [[ $EUID -eq 0 ]]; then
        log_info "当前用户为 root，继续执行"
        SUDO_CMD=""
        elif command -v sudo >/dev/null 2>&1; then
        if sudo -n true 2>/dev/null; then
            log_info "当前用户有 sudo 权限，继续执行"
            SUDO_CMD="sudo"
        else
            log_error "当前用户没有 sudo 权限，请使用 root 用户运行或配置 sudo"
            exit 1
        fi
    else
        log_error "系统中未安装 sudo，请使用 root 用户运行"
        exit 1
    fi
}

# 检查操作系统
check_os() {
    log_info "检查操作系统..."

    if [[ ! -f /etc/os-release ]]; then
        log_error "/etc/os-release 文件不存在，无法确定操作系统"
        exit 1
    fi

    # 加载操作系统信息
    . /etc/os-release

    log_info "检测到操作系统: ${NAME} ${VERSION}"

    # 检查是否为支持的发行版
    case "${ID}" in
        debian|ubuntu)
            log_success "支持的操作系统: ${ID}"
        ;;
        *)
            log_error "不支持的操作系统: ${ID}。此脚本仅支持 Debian 和 Ubuntu"
            exit 1
        ;;
    esac

    # 检查版本代号是否存在
    if [[ -z "${VERSION_CODENAME:-}" ]]; then
        log_error "无法获取发行版代号 (VERSION_CODENAME)"
        exit 1
    fi

    log_info "发行版代号: ${VERSION_CODENAME}"

    # 验证代号是否为支持的版本
    case "${VERSION_CODENAME}" in
        # Debian
        bullseye|bookworm|trixie|sid)
            log_success "支持的 Debian 版本: ${VERSION_CODENAME}"
        ;;
        # Ubuntu
        focal|jammy|mantic|noble)
            log_success "支持的 Ubuntu 版本: ${VERSION_CODENAME}"
        ;;
        *)
            log_warning "未明确验证的发行版代号: ${VERSION_CODENAME}"
            log_warning "脚本将继续执行，但可能不受官方支持"
            read -p "是否继续？(y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                log_info "用户取消操作"
                exit 0
            fi
        ;;
    esac
}

# 检查网络连接
check_network() {
    log_info "检查网络连接..."

    if ! command -v curl >/dev/null 2>&1; then
        log_warning "curl 未安装，将在后续步骤中安装"
        return
    fi

    if ! curl -s --max-time 10 --head https://www.postgresql.org >/dev/null; then
        log_error "无法连接到 PostgreSQL 官方网站，请检查网络连接"
        exit 1
    fi

    log_success "网络连接正常"
}

# 安装必要的依赖包
install_dependencies() {
    log_info "安装必要的依赖包..."

    # 更新包列表
    log_info "更新软件包列表..."
    if ! $SUDO_CMD apt update; then
        log_error "更新软件包列表失败"
        exit 1
    fi

    # 安装依赖
    local packages="curl ca-certificates"
    log_info "安装依赖包: $packages"

    if ! $SUDO_CMD apt install -y $packages; then
        log_error "安装依赖包失败"
        exit 1
    fi

    log_success "依赖包安装完成"
}

# 创建目录并导入密钥
import_repository_key() {
    log_info "导入 PostgreSQL 仓库密钥..."

    local pgdg_dir="/usr/share/postgresql-common/pgdg"
    local key_file="$pgdg_dir/apt.postgresql.org.asc"
    local key_url="https://www.postgresql.org/media/keys/ACCC4CF8.asc"

    # 创建目录
    log_info "创建目录: $pgdg_dir"
    if ! $SUDO_CMD install -d "$pgdg_dir"; then
        log_error "创建目录失败: $pgdg_dir"
        exit 1
    fi

    # 检查目录是否存在且可写
    if [[ ! -d "$pgdg_dir" ]]; then
        log_error "目录创建失败或不存在: $pgdg_dir"
        exit 1
    fi

    # 下载密钥
    log_info "从 $key_url 下载密钥..."
    if ! $SUDO_CMD curl -o "$key_file" --fail --silent --show-error --location "$key_url"; then
        log_error "下载 PostgreSQL 仓库密钥失败"
        exit 1
    fi

    # 验证密钥文件
    if [[ ! -f "$key_file" ]]; then
        log_error "密钥文件下载失败: $key_file"
        exit 1
    fi

    # 检查文件大小
    local file_size=$(stat -c%s "$key_file" 2>/dev/null || echo "0")
    if [[ "$file_size" -lt 100 ]]; then
        log_error "密钥文件似乎不完整，大小: $file_size 字节"
        exit 1
    fi

    # 验证密钥格式
    if ! grep -q "BEGIN PGP PUBLIC KEY BLOCK" "$key_file"; then
        log_error "密钥文件格式不正确"
        exit 1
    fi

    log_success "PostgreSQL 仓库密钥导入成功"
}

# 创建 APT 源文件 (deb822 格式)
create_apt_source() {
    log_info "创建 APT 源文件 (deb822 格式)..."

    # 重新加载操作系统信息以确保变量可用
    . /etc/os-release

    local sources_dir="/etc/apt/sources.list.d"
    local source_file="$sources_dir/pgdg.sources"
    local key_file="/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc"

    # 检查源目录是否存在
    if [[ ! -d "$sources_dir" ]]; then
        log_error "APT 源目录不存在: $sources_dir"
        exit 1
    fi

    # 检查密钥文件是否存在
    if [[ ! -f "$key_file" ]]; then
        log_error "密钥文件不存在: $key_file"
        exit 1
    fi

    # 构造 deb822 格式的源文件内容
    local source_content="Types: deb
URIs: https://apt.postgresql.org/pub/repos/apt
Suites: ${VERSION_CODENAME}-pgdg
Components: main
Signed-By: $key_file"

    log_info "创建源文件: $source_file"
    log_info "使用 deb822 格式"

    # 创建源文件
    if ! echo "$source_content" | $SUDO_CMD tee "$source_file" >/dev/null; then
        log_error "创建 APT 源文件失败"
        exit 1
    fi

    # 验证文件创建
    if [[ ! -f "$source_file" ]]; then
        log_error "源文件创建失败: $source_file"
        exit 1
    fi

    # 验证文件内容
    if ! grep -q "postgresql.org" "$source_file"; then
        log_error "源文件内容不正确"
        exit 1
    fi

    # 验证 deb822 格式的必要字段
    if ! grep -q "Types:" "$source_file" || ! grep -q "URIs:" "$source_file" || ! grep -q "Suites:" "$source_file"; then
        log_error "deb822 格式源文件字段不完整"
        exit 1
    fi

    log_success "APT 源文件 (deb822 格式) 创建成功"
    log_info "源文件内容:"
    echo "---"
    cat "$source_file" 2>/dev/null || log_warning "无法显示源文件内容"
    echo "---"
}

# 更新软件包列表
update_package_list() {
    log_info "更新软件包列表以包含 PostgreSQL 仓库..."

    if ! $SUDO_CMD apt update; then
        log_error "更新软件包列表失败"
        exit 1
    fi

    # 验证 PostgreSQL 包是否可用
    if apt-cache search postgresql | grep -q "postgresql"; then
        log_success "PostgreSQL 仓库配置成功，可以安装 PostgreSQL"
    else
        log_warning "PostgreSQL 包可能不可用，请检查仓库配置"
    fi
}

# 显示安装信息
show_installation_info() {
    log_success "PostgreSQL 官方仓库配置完成！"
    echo
    log_info "已使用 deb822 格式创建源文件: /etc/apt/sources.list.d/pgdg.sources"
    log_info "deb822 格式的优势: 更结构化、可读性更好、支持更多功能"
    echo
    log_info "现在您可以安装 PostgreSQL："
    echo "  # 安装最新版本的 PostgreSQL"
    echo "  sudo apt install postgresql postgresql-contrib"
    echo
    log_info "查看可用版本："
    echo "  apt-cache search postgresql | grep postgresql-"
    echo
}

# 主函数
main() {
    log_info "开始配置 PostgreSQL 官方仓库..."
    echo

    # 执行所有检查和安装步骤
    check_privileges
    check_os
    check_network
    install_dependencies
    import_repository_key
    create_apt_source
    update_package_list
    show_installation_info

    log_success "脚本执行完成！"
}

# 捕获错误并清理
cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log_error "脚本执行失败，退出代码: $exit_code"
    fi
    exit $exit_code
}

# 设置错误处理
trap cleanup EXIT

# 执行主函数
main "$@"