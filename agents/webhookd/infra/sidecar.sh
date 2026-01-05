#!/bin/bash
set -euo pipefail

declare -A DEFAULT_INSTALL_PATH
DEFAULT_INSTALL_PATH["windows"]="C:\\fusion-collectors\\"
DEFAULT_INSTALL_PATH["linux"]="/opt/"

declare -A DEFAULT_INSTALL_SCRIPT

DEFAULT_INSTALL_SCRIPT["windows"]=$(
    cat <<'EOF'
#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Install and configure the collector sidecar service.

.DESCRIPTION
    This script generates the sidecar configuration file and registers/starts the Windows service.
    Configure the variables below before running the script.
#>

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ============================================
# 配置区域 - 使用占位符，可通过 sed 等工具替换
# ============================================

# [必需] Token for sidecar to get configuration
$ApiToken = "${API_TOKEN}"

# [必需] Bklite access endpoint URL
# Example: http://10.10.10.10:20005/node_mgmt/open_api/node
$ServerUrl = "${SERVER_URL}"

# [必需] Node ID for the sidecar (usually the machine IP or hostname)
$NodeId = "${NODE_ID}"

# [可选] Zone ID for the sidecar (default: 1)
$ZoneId = "${ZONE_ID}"

# [可选] Node Name for the sidecar (default: "")
$NodeName = "${NODE_NAME}"

# [可选] Group ID for the sidecar (default: 1)
$GroupId = "${GROUP_ID}"

# [可选] URL to download the collector package (zip file)
# Leave empty if you have already extracted the package to the installation directory
$DownloadUrl = "${DOWNLOAD_URL}"

# [可选] Installation directory (default: C:\collector-sidecar\)
$InstallDir = "${INSTALL_DIR}"

# ============================================
# 以下为脚本代码，请勿修改
# ============================================

$PROGRAM = $MyInvocation.MyCommand.Name
$VERSION = "1.0"
$EXITCODE = 0
$INSTALL_PATH = ""

function Download-Package {
    param (
        [string]$Url,
        [string]$DestinationDir
    )
    
    Write-Host "Downloading collector package from: $Url"
    
    # Ensure destination directory exists
    if (-not (Test-Path -Path $DestinationDir)) {
        New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null
        Write-Host "Created installation directory: $DestinationDir"
    }
    
    # Generate temp file path for the zip
    $tempZipFile = Join-Path -Path $env:TEMP -ChildPath "collector-package-$(Get-Date -Format 'yyyyMMddHHmmss').zip"
    
    try {
        # Download the zip file
        Write-Host "Downloading to temporary file: $tempZipFile"
        
        # Use TLS 1.2 for secure connections
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        
        # Try using Invoke-WebRequest first (more features)
        try {
            $ProgressPreference = 'SilentlyContinue'  # Speeds up download
            Invoke-WebRequest -Uri $Url -OutFile $tempZipFile -UseBasicParsing
        } catch {
            # Fallback to WebClient for older PowerShell versions
            Write-Host "Falling back to WebClient..."
            $webClient = New-Object System.Net.WebClient
            $webClient.DownloadFile($Url, $tempZipFile)
        }
        
        Write-Host "Download completed successfully"
        
        # Verify the file was downloaded
        if (-not (Test-Path -Path $tempZipFile)) {
            throw "Downloaded file not found: $tempZipFile"
        }
        
        $fileSize = (Get-Item $tempZipFile).Length
        Write-Host "Downloaded file size: $([math]::Round($fileSize / 1MB, 2)) MB"
        
        # Extract the zip file
        Write-Host "Extracting package to: $DestinationDir"
        
        # Use Expand-Archive (PowerShell 5.0+) or fall back to .NET
        try {
            Expand-Archive -Path $tempZipFile -DestinationPath $DestinationDir -Force
        } catch {
            # Fallback for older PowerShell versions
            Write-Host "Falling back to .NET extraction..."
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            [System.IO.Compression.ZipFile]::ExtractToDirectory($tempZipFile, $DestinationDir)
        }
        
        Write-Host "Package extracted successfully"
        
    } catch {
        Write-Host "Error downloading or extracting package: $_" -ForegroundColor Red
        throw
    } finally {
        # Clean up temp file
        if (Test-Path -Path $tempZipFile) {
            Remove-Item -Path $tempZipFile -Force
            Write-Host "Cleaned up temporary file"
        }
    }
}

function Generate-Config {
    param (
        [string]$ServerUrl,
        [string]$ApiToken,
        [string]$NodeId,
        [string]$ZoneId,
        [string]$GroupId
    )
    
    $configPath = "${INSTALL_PATH}sidecar.yml"
    $configContent = @"
server_url: "$ServerUrl"
server_api_token: "$ApiToken"
node_id: "$NodeId"
node_name: "$NodeName"
update_interval: 10
tls_skip_verify: false
send_status: true
list_log_files: []
cache_path: "${INSTALL_PATH}cache"
log_path: "${INSTALL_PATH}logs"
log_rotate_max_file_size: "10MiB"
log_rotate_keep_files: 5
collector_validation_timeout: "1m"
collector_shutdown_timeout: "10s"
collector_configuration_directory: "${INSTALL_PATH}generated"
windows_drive_range: ""
tags: ["cloud:$ZoneId", "group:$GroupId", "install_method:manual", "node_type:container"]
collector_binaries_accesslist:
- "${INSTALL_PATH}bin\*"
"@
    
    try {
        Set-Content -Path $configPath -Value $configContent -Encoding UTF8
        Write-Host "Configuration file generated successfully: $configPath"
        
        # Verify config file was created
        if (-not (Test-Path -Path $configPath)) {
            throw "Configuration file was not created successfully"
        }
    } catch {
        Write-Host "Error generating configuration file: $_" -ForegroundColor Red
        throw
    }
}

function Register-Service {
    # Verify collector-sidecar.exe exists
    $exePath = "${INSTALL_PATH}collector-sidecar.exe"
    if (-not (Test-Path -Path $exePath)) {
        throw "Collector executable not found: $exePath. Please ensure the package is downloaded and extracted correctly."
    }
    Write-Host "Verified collector executable: $exePath"
    
    # Register service to Windows service, create service with minimal parameters
    $binPath = "${INSTALL_PATH}collector-sidecar.exe -c ${INSTALL_PATH}sidecar.yml"
    
    # Check if service already exists
    $existingService = Get-Service -Name "sidecar" -ErrorAction SilentlyContinue
    if ($existingService) {
        Write-Host "Service already exists, stopping and removing..."
        Stop-Service -Name "sidecar" -Force -ErrorAction SilentlyContinue
        sc.exe delete sidecar
        
        # Wait for service to be fully deleted (up to 10 seconds)
        $maxAttempts = 10
        $attempt = 0
        do {
            Start-Sleep -Seconds 1
            $attempt++
            $stillExists = Get-Service -Name "sidecar" -ErrorAction SilentlyContinue
        } while ($stillExists -and $attempt -lt $maxAttempts)
        
        if ($stillExists) {
            Write-Host "Warning: Service may not be fully deleted" -ForegroundColor Yellow
        } else {
            Write-Host "Service deleted successfully"
        }
    }
    
    # Create service
    $createResult = sc.exe create sidecar binPath= "$binPath" start= auto
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create service. Error code: $LASTEXITCODE. Output: $createResult"
    }
    Write-Host "Service registered successfully"
    
    # Start service
    Write-Host "Starting service..."
    $startResult = sc.exe start sidecar
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 1056) {  # 1056 = service already running
        Write-Host "Failed to start service. Error code: $LASTEXITCODE" -ForegroundColor Yellow
    }
    
    # Wait and check service status (up to 15 seconds)
    $maxWait = 15
    $waited = 0
    $serviceRunning = $false
    
    Write-Host "Waiting for service to start..."
    while ($waited -lt $maxWait) {
        Start-Sleep -Seconds 1
        $waited++
        $service = Get-Service -Name "sidecar" -ErrorAction SilentlyContinue
        if ($service -and $service.Status -eq "Running") {
            $serviceRunning = $true
            break
        }
    }
    
    if ($serviceRunning) {
        Write-Host "Service started successfully" -ForegroundColor Green
    } else {
        $serviceStatus = if ($service) { $service.Status } else { "Not Found" }
        throw "Service startup failed. Current status: $serviceStatus. Check logs at: ${INSTALL_PATH}logs"
    }
}

# Main execution flow with error handling
try {
    Write-Host "="*60
    Write-Host "Collector Sidecar Installation Script v$VERSION"
    Write-Host "="*60
    Write-Host ""
    
    # Set installation path
    $script:INSTALL_PATH = $InstallDir
    if (-not $INSTALL_PATH.EndsWith("\")) {
        $script:INSTALL_PATH = "$INSTALL_PATH\"
    }
    Write-Host "Installation directory: $INSTALL_PATH"
    
    # Download package if URL is provided
    if (-not [string]::IsNullOrEmpty($DownloadUrl)) {
        Write-Host ""
        Download-Package -Url $DownloadUrl -DestinationDir $INSTALL_PATH
    } else {
        # Verify installation directory exists
        if (-not (Test-Path -Path $INSTALL_PATH)) {
            Write-Host "Installation directory does not exist: $INSTALL_PATH" -ForegroundColor Red
            Write-Host "Please provide -DownloadUrl to download the package, or manually extract it to this location."
            throw "Installation directory not found"
        }
    }
    
    # Ensure we're in the installation directory
    if (-not (Test-Path -Path $INSTALL_PATH)) {
        throw "Installation directory does not exist: $INSTALL_PATH"
    }
    Set-Location -Path $INSTALL_PATH
    Write-Host "Working directory: $(Get-Location)"
    Write-Host ""
    
    # Generate configuration
    Write-Host "Generating configuration file..."
    Generate-Config -ServerUrl $ServerUrl -ApiToken $ApiToken -NodeId $NodeId -ZoneId $ZoneId -GroupId $GroupId
    Write-Host ""
    
    # Register and start service
    Write-Host "Registering and starting service..."
    Register-Service
    
    Write-Host ""
    Write-Host "="*60
    Write-Host "Installation completed successfully!" -ForegroundColor Green
    Write-Host "="*60
    Write-Host ""
    Write-Host "Service Name: sidecar"
    Write-Host "Config File: ${INSTALL_PATH}sidecar.yml"
    Write-Host "Logs Location: ${INSTALL_PATH}logs"
    Write-Host ""
    Write-Host "You can check service status with: Get-Service -Name sidecar"
    Write-Host "You can view logs at: ${INSTALL_PATH}logs"
    
    $script:EXITCODE = 0
    
} catch {
    Write-Host ""
    Write-Host "="*60 -ForegroundColor Red
    Write-Host "Installation failed!" -ForegroundColor Red
    Write-Host "="*60 -ForegroundColor Red
    Write-Host ""
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please check the error message above and try again."
    Write-Host "For help, run: .\$PROGRAM -Help"
    
    $script:EXITCODE = 1
}

exit $EXITCODE
EOF
)

DEFAULT_INSTALL_SCRIPT["linux"]=$(
    cat <<'EOF'
#!/bin/bash

cd ${INSTALL_DIR}

# 检查root权限
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "错误: 请使用 root 权限运行此脚本"
        exit 1
    fi
}

# 安装服务
install_service() {
    echo "开始安装 Fusion Collector Sidecar 服务..."

    # 替换配置文件中的占位符
    sed -i "s|__SERVER__URL__|$SERVER_URL|g" ${INSTALL_DIR}/fusion-collectors/sidecar.yml
    sed -i "s|__SERVER__API__TOKEN__|$SERVER_API_TOKEN|g" ${INSTALL_DIR}/fusion-collectors/sidecar.yml
    sed -i "s|__TAGS__|\"cloud:$ZONE\", \"group:$GROUP\", \"install_method:manual\"|g" ${INSTALL_DIR}/fusion-collectors/sidecar.yml
    sed -i "s|__NODE__NAME__|$NODE_NAME|g" ${INSTALL_DIR}/fusion-collectors/sidecar.yml

    # 拷贝服务文件并启用
    cp -f "./sidecar.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable --now sidecar.service

    if [ $? -eq 0 ]; then
        echo "服务已成功启动并设置为开机自启动"
    else
        echo "警告: 服务启动过程中出现问题，请检查系统日志"
    fi
}

download_package() {
    echo "下载并解压 Collector 包..."

    TMPDIR=$(mktemp -d)
    curl -k -L "${DOWNLOAD_URL}" -o "${TMPDIR}/collector-package.zip"
    unzip -o "${TMPDIR}/collector-package.zip" -d "${INSTALL_DIR}/"
    rm -rf "${TMPDIR}"

    echo "Collector 包下载并解压完成"
}

# 主函数
main() {
    # 解析参数
    SERVER_URL=${SERVER_URL}
    SERVER_API_TOKEN=${API_TOKEN}
    ZONE=${ZONE_ID}
    GROUP=${GROUP_ID}
    NODE_NAME="${NODE_NAME}"
    NODE_ID=${NODE_ID}

    # download package
    download_package
    
    cd "${INSTALL_DIR}/fusion-collectors"

    echo "$NODE_ID" > ./node-id
    echo "Node ID 已写入到 ./node-id 文件"
    # 安装服务
    install_service

    echo "安装完成"
    exit 0
}

# 执行主函数
main "$@"

EOF
)

# 返回成功的 JSON 响应（支持多行内容）
json_success() {
    local id="$1"
    local message="$2"
    shift 2
    
    # 使用 jq 构建 JSON，确保正确转义
    local json
    json=$(jq -n --arg id "$id" --arg message "$message" '{status: "success", id: $id, message: $message}')
    
    # 添加额外的字段
    while [ $# -gt 0 ]; do
        json=$(echo "$json" | jq --arg key "$1" --arg value "$2" '. + {($key): $value}')
        shift 2
    done
    
    echo "$json"
}

# 返回错误的 JSON 响应
json_error() {
    local id="$1"
    local message="$2"
    local error="${3:-}"
    
    if [ -n "$error" ]; then
        jq -n --arg id "$id" --arg message "$message" --arg error "$error" \
            '{status: "error", id: $id, message: $message, error: $error}'
    else
        jq -n --arg id "$id" --arg message "$message" \
            '{status: "error", id: $id, message: $message}'
    fi
}

# 参数校验函数
validate_param() {
    local param_name="$1"
    local param_value="$2"
    local validation_type="$3"
    local node_id="${4:-}"
    
    case "$validation_type" in
        required)
            [ -n "$param_value" ] || { json_error "$node_id" "Missing required parameter: $param_name"; exit 1; }
            ;;
        enum)
            local allowed_values="$4"
            echo "$allowed_values" | grep -qw "$param_value" || \
                { json_error "$node_id" "Invalid $param_name: '$param_value'. Allowed values: $allowed_values"; exit 1; }
            ;;
        url)
            [ -z "$param_value" ] || echo "$param_value" | grep -qE '^https?://' || \
                { json_error "$node_id" "Invalid $param_name format. Must start with http:// or https://"; exit 1; }
            ;;
        positive_int)
            echo "$param_value" | grep -qE '^[0-9]+$' || \
                { json_error "$node_id" "Invalid $param_name: must be a positive integer"; exit 1; }
            ;;
    esac
}

# 检查依赖和输入数据
command -v jq &> /dev/null || \
    { echo '{"status": "error", "message": "jq command not found. Please install jq to run this script."}' >&2; exit 1; }

JSON_DATA="${1:-$(cat)}"
[ -n "$JSON_DATA" ] || { json_error "" "No input data provided"; exit 1; }
echo "$JSON_DATA" | jq empty 2>/dev/null || { json_error "" "Invalid JSON format"; exit 1; }

# 提取所有参数
OS=$(echo "$JSON_DATA" | jq -r '.os')
FILE_URL=$(echo "$JSON_DATA" | jq -r '.file_url')
API_TOKEN=$(echo "$JSON_DATA" | jq -r '.api_token')
SERVER_URL=$(echo "$JSON_DATA" | jq -r '.server_url')
NODE_ID=$(echo "$JSON_DATA" | jq -r '.node_id')
ZONE_ID=$(echo "$JSON_DATA" | jq -r '.zone_id')
GROUP_ID=$(echo "$JSON_DATA" | jq -r '.group_id')
NODE_NAME=$(echo "$JSON_DATA" | jq -r '.node_name')

# 参数校验（优雅的声明式风格）
validate_param "os" "$OS" "required"
validate_param "os" "$OS" "enum" "linux windows"
validate_param "node_id" "$NODE_ID" "required"
validate_param "node_name" "$NODE_NAME" "required"
validate_param "api_token" "$API_TOKEN" "required" "$NODE_ID"
validate_param "server_url" "$SERVER_URL" "required" "$NODE_ID"
validate_param "server_url" "$SERVER_URL" "url" "$NODE_ID"
validate_param "file_url" "$FILE_URL" "url" "$NODE_ID"
validate_param "zone_id" "$ZONE_ID" "positive_int" "$NODE_ID"
validate_param "group_id" "$GROUP_ID" "positive_int" "$NODE_ID"

INSTALL_DIR=${DEFAULT_INSTALL_PATH["$OS"]}
SCRIPT_TEMPLATE=${DEFAULT_INSTALL_SCRIPT["$OS"]}

INSTALL_SCRIPT="$SCRIPT_TEMPLATE"

declare -A replacements=(
  [DOWNLOAD_URL]="$FILE_URL"
  [API_TOKEN]="$API_TOKEN"
  [SERVER_URL]="$SERVER_URL"
  [NODE_ID]="$NODE_ID"
  [ZONE_ID]="$ZONE_ID"
  [GROUP_ID]="$GROUP_ID"
  [INSTALL_DIR]="$INSTALL_DIR"
  [NODE_NAME]="$NODE_NAME"
)

for key in "${!replacements[@]}"; do
  INSTALL_SCRIPT="${INSTALL_SCRIPT//\$\{$key\}/${replacements[$key]}}"
done

# 返回成功的 JSON 响应，包含生成的安装脚本
json_success "$NODE_ID" "Installation script generated successfully" "install_script" "$INSTALL_SCRIPT"
exit 0