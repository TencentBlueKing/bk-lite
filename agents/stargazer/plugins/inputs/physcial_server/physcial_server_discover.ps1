# Requires -RunAsAdministrator
$ErrorActionPreference = "SilentlyContinue"

# ========== 判断是否为测试环境 IP (示例逻辑) ==========
$current_ips = Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress
if ($current_ips -contains "xxxxxxxx") {
    # 模拟测试环境输出
    Write-Output "=== board_info ==="
    Write-Output "board_vendor=Huawei"
    Write-Output "board_model=BC82AMDQ"
    Write-Output "board_serial=2106411443FSP9001051"
    Write-Output ""
    Write-Output "=== system_sn ==="
    Write-Output "serial_number=2102355RECP0PB100025"
    # ... (此处省略测试环境的硬编码输出，逻辑与Shell一致，直接退出)
    exit 0
}

# ========== 判断是否为物理服务器 ==========
$systemInfo = Get-CimInstance Win32_ComputerSystem
$biosInfo = Get-CimInstance Win32_BIOS
$model = $systemInfo.Model
$manufacturer = $systemInfo.Manufacturer

if ($model -match "VMware|VirtualBox|KVM|Bochs|QEMU" -or $manufacturer -match "VMware|Microsoft Corporation|Xen") {
    Write-Output "这是虚拟机"
    exit 0
}

# ========== board_info ==========
Write-Output "`n=== board_info ==="
$board = Get-CimInstance Win32_BaseBoard
Write-Output ("board_vendor=" + ($board.Manufacturer -replace "^\s+|\s+$",""))
Write-Output ("board_model=" + ($board.Product -replace "^\s+|\s+$",""))
Write-Output ("board_serial=" + ($board.SerialNumber -replace "^\s+|\s+$",""))

# ========== system_sn ==========
Write-Output "`n=== system_sn ==="
Write-Output ("serial_number=" + ($biosInfo.SerialNumber -replace "^\s+|\s+$",""))

# ========== CPU_info ==========
Write-Output "`n=== CPU_info ==="
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$totalCores = (Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum
$totalThreads = (Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum

Write-Output ("cpu_arch=" + $env:PROCESSOR_ARCHITECTURE)
Write-Output ("cpu_vendor=" + ($cpu.Manufacturer -replace "^\s+|\s+$",""))
Write-Output ("cpu_model=" + ($cpu.Name -replace "^\s+|\s+$",""))
Write-Output ("cpu_cores=" + $totalCores)
Write-Output ("cpu_threads=" + $totalThreads)
Write-Output ("cpu_virtualization=" + $(if ($cpu.VirtualizationFirmwareEnabled) { "Enabled" } else { "N/A" }))
Write-Output ("cpu_mhz_min=N/A") # Windows 通常不直接提供 Min MHz
Write-Output ("cpu_mhz_max=" + $cpu.MaxClockSpeed)

# ========== disk_info ==========
Write-Output "`n=== disk_info ==="
$disks = Get-PhysicalDisk | Sort-Object DeviceId

foreach ($disk in $disks) {
    # 排除一些非物理盘
    if ($disk.BusType -eq "File Backed Virtual") { continue }

    $sizeGB = [math]::Round($disk.Size / 1GB, 1).ToString() + "G"
    $mediaType = if ($disk.MediaType -eq "SSD") { "SSD" } elseif ($disk.MediaType -eq "HDD") { "HDD" } else { "Unknown" }
    
    # 尝试获取设备路径名称 (类似 /dev/sda)，Windows下通常是 PhysicalDriveX
    $diskName = "PhysicalDrive" + $disk.DeviceId

    Write-Output ("disk_name=" + $diskName)
    Write-Output ("disk_vendor=" + ($disk.Manufacturer -replace "^\s+|\s+$",""))
    Write-Output ("disk_model=" + ($disk.Model -replace "^\s+|\s+$",""))
    Write-Output ("disk=" + $sizeGB)
    Write-Output ("disk_tran=" + $disk.BusType)
    Write-Output ("disk_type=" + $mediaType)
    Write-Output ("disk_sn=" + ($disk.SerialNumber -replace "^\s+|\s+$",""))
    Write-Output ""
}

# ========== mem_info ==========
Write-Output "`n=== mem_info ==="
$mems = Get-CimInstance Win32_PhysicalMemory

foreach ($mem in $mems) {
    $sizeGB = [math]::Round($mem.Capacity / 1GB, 0).ToString() + " GB"
    # 内存类型映射表 (SMBIOS Memory Type)
    $memTypeMap = @{ 20="DDR"; 21="DDR2"; 24="DDR3"; 26="DDR4"; 30="LPDDR4"; 34="DDR5" }
    $typeStr = if ($memTypeMap.ContainsKey($mem.SMBIOSMemoryType)) { $memTypeMap[$mem.SMBIOSMemoryType] } else { "Unknown" }

    Write-Output ("mem_locator=" + $mem.DeviceLocator + " " + $mem.BankLabel)
    Write-Output ("mem_vendor=" + $mem.Manufacturer)
    Write-Output ("mem_part_number=" + ($mem.PartNumber -replace "^\s+|\s+$",""))
    Write-Output ("mem_type=" + $typeStr)
    Write-Output ("mem_size=" + $sizeGB)
    Write-Output ("mem_sn=" + $mem.SerialNumber)
    Write-Output ""
}

# ========== GPU info ==========
Write-Output "`n=== GPU info ==="
$gpus = Get-CimInstance Win32_VideoController
foreach ($gpu in $gpus) {
    Write-Output ("gpu_name=" + $gpu.DeviceID) # Windows下通常是 PCI\VEN_xxxx...
    Write-Output ("gpu_type=" + $gpu.VideoProcessor)
    Write-Output ("gpu_desc=" + $gpu.Name + " " + $gpu.Description)
    
    # 尝试获取 NVIDIA 显卡详细信息
    # if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        # $nvidiaInfo = nvidia-smi --query-gpu=serial,uuid --format=csv,noheader,nounits | Select-Object -First 1
        # if ($nvidiaInfo) {
           # Write-Output ("gpu_desc_ext=" + $nvidiaInfo)
        # }
    # }
    Write-Output ""
}

# ========== NIC info ==========
Write-Output "`n=== NIC info ==="
$nics = Get-NetAdapter -Physical | Sort-Object PnpDeviceID

foreach ($nic in $nics) {
    # 获取 PCI 地址信息需要解析 PnpDeviceID 或使用 Get-NetAdapterHardwareInfo
    $hardwareInfo = Get-NetAdapterHardwareInfo -Name $nic.Name
    $pciAddr = $hardwareInfo.Bus.ToString() + ":" + $hardwareInfo.Device.ToString() + "." + $hardwareInfo.Function.ToString()

    Write-Output "--------------------------------------"
    Write-Output ("nic_pci_addr=" + $pciAddr)
    Write-Output ("nic_type=" + $nic.InterfaceDescription)
    Write-Output ("nic_vendor=" + $nic.DriverProvider) # Windows下DriverProvider通常对应厂商
    Write-Output ("nic_model=" + $nic.InterfaceDescription)
    Write-Output ("nic_iface=" + $nic.Name) # 类似 Ethernet 2
    Write-Output ("nic_mac=" + ($nic.MacAddress -replace "-",":"))
    Write-Output "--------------------------------------"
}

# ========== 扩展硬件信息 ==========
Write-Output "`n`n【扩展硬件信息】"

Write-Output "`n=== 机箱信息 ==="
$chassis = Get-CimInstance Win32_SystemEnclosure
Write-Output ("Manufacturer: " + $chassis.Manufacturer)
Write-Output ("Type: " + $chassis.ChassisTypes)
Write-Output ("Serial Number: " + $chassis.SerialNumber)
Write-Output ("Asset Tag: " + $chassis.SMBIOSAssetTag)

Write-Output "`n=== bios_info ==="
Write-Output ("bios_vendor=" + $biosInfo.Manufacturer)
Write-Output ("bios_version=" + $biosInfo.SMBIOSBIOSVersion)
# 格式化日期
$dateObj = $biosInfo.ReleaseDate
if ($dateObj -is [DateTime]) {
    $dateStr = $dateObj.ToString("MM/dd/yyyy")
} else {
    $dateStr = $dateObj
}
Write-Output ("bios_release_date=" + $dateStr)

Write-Output "`n=== RAID 控制器 ==="
# Windows通常没有通用命令获取RAID卡详情，需要依赖厂商工具
# 这里列出如果存在特定工具的逻辑
if (Test-Path "C:\Program Files (x86)\MegaRAID Storage Manager\StorCLI.exe") {
    # & "C:\Program Files (x86)\MegaRAID Storage Manager\StorCLI.exe" /c0 show
} else {
    Write-Output "未检测到常见 RAID 控制器工具(StorCLI等)"
}

Write-Output "`n=== power_info ==="
# Windows WMI 通常无法直接获取电源信息，除非安装了厂商的 WMI Provider (如 Dell OpenManage)
# 这里仅做简单的 WMI 尝试，通常为空
$powerSupplies = Get-CimInstance CIM_PowerSupply -ErrorAction SilentlyContinue
if ($powerSupplies) {
    foreach ($p in $powerSupplies) {
        Write-Output ("power_name=" + $p.DeviceID)
        Write-Output ("power_manufacturer=" + $p.Manufacturer)
        Write-Output ("power_serial=" + $p.SerialNumber)
        Write-Output ("power_max_capacity=" + $p.MaxPowerOutput)
        Write-Output ""
    }
} else {
    Write-Output "无法通过标准WMI获取电源信息(可能需要厂商驱动)"
}

Write-Output "`n=== NVMe 设备列表 ==="
# 使用 PowerShell 获取 NVMe 盘
Get-PhysicalDisk | Where-Object { $_.BusType -eq "NVMe" } | Select-Object FriendlyName, SerialNumber, Size | Format-Table -HideTableHeaders

Write-Output "`n=== 硬盘 WWN ==="
# 获取 UniqueId (对应 WWN/EUI)
foreach ($disk in $disks) {
    if ($disk.BusType -ne "File Backed Virtual") {
       Write-Output ("PhysicalDrive" + $disk.DeviceId + ": " + $disk.UniqueId)
    }
}

Write-Output "`n=== FC HBA WWN ==="
# 获取 FC HBA 信息
$fcAdapters = Get-InitiatorPort -ErrorAction SilentlyContinue | Where-Object { $_.PortAddressFamily -eq "FibreChannel" }
if ($fcAdapters) {
    foreach ($fc in $fcAdapters) {
        Write-Output ("NodeWWN=" + $fc.NodeAddress + " PortWWN=" + $fc.PortAddress)
    }
} else {
    Write-Output "未检测到 FC HBA 卡"
}