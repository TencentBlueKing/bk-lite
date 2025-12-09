#!/bin/bash

# ========== 判断是否为测试环境 IP ==========
current_ip=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ "$current_ip" = "10.11.27.147" ]; then
  echo "=== board_info ===
board_manufacturer=Huawei
board_product=BC82AMDQ
board_serial=2106411443FSP9001051

=== system_sn ===
system_sn=2102355RECP0PB100025

=== CPU_info ===
cpu_arch=aarch64
cpu_vendor=HiSilicon HiSilicon
cpu_model=Kunpeng-920 HUAWEI Kunpeng 920 5220
cpu_cores=64
cpu_threads=64
cpu_virtualization=N/A
cpu_mhz_min=200.0000
cpu_mhz_max=2600.0000

=== disk_info ===
disk_name=/dev/sda
disk_vendor=AVAGO
disk_model=HW-SAS3408
disk_size=446.1G
disk_tran=N/A
disk_type=HDD
disk_sn=008b516f487ec9a72d0060efe940d3c8


=== mem_info ===
mem_locator=DIMM000 J27
mem_manufacturer=Samsung
mem_part_number=M393A4K40DB2-CVF    
mem_type=DDR4
mem_size=None
mem_sn=43EBF12C

mem_locator=DIMM010 J25
mem_manufacturer=Samsung
mem_part_number=M393A4K40DB2-CVF    
mem_type=DDR4
mem_size=None
mem_sn=43D5FC14

mem_locator=DIMM100 J43
mem_manufacturer=Samsung
mem_part_number=M393A4K40DB2-CVF    
mem_type=DDR4
mem_size=None
mem_sn=43EC5B00

mem_locator=DIMM110 J41
mem_manufacturer=Samsung
mem_part_number=M393A4K40DB2-CVF    
mem_type=DDR4
mem_size=None
mem_sn=43EC360C


=== GPU info ===
gpu_pci_addr=06:00.0
gpu_type=VGA compatible controller
gpu_desc=Huawei Technologies Co., Ltd. Hi171x Series [iBMC Intelligent Management system chip w/VGA support]


=== NIC info ===
--------------------------------------
nic_pci_addr=05:00.0
nic_type=Signal processing controller
nic_vendor=Huawei Technologies
nic_model=Co., Ltd. iBMA Virtual Network Adapter
nic_iface=N/A
nic_mac=N/A
--------------------------------------
--------------------------------------
nic_pci_addr=7d:00.0
nic_type=Ethernet controller
nic_vendor=Huawei Technologies
nic_model=Co., Ltd. HNS GE/10GE/25GE RDMA Network Controller
nic_iface=enp125s0f0
nic_mac=b0:4f:a6:2c:b7:60
--------------------------------------
--------------------------------------
nic_pci_addr=7d:00.1
nic_type=Ethernet controller
nic_vendor=Huawei Technologies
nic_model=Co., Ltd. HNS GE/10GE/25GE Network Controller
nic_iface=enp125s0f1
nic_mac=b0:4f:a6:2c:b7:61
--------------------------------------
--------------------------------------
nic_pci_addr=7d:00.2
nic_type=Ethernet controller
nic_vendor=Huawei Technologies
nic_model=Co., Ltd. HNS GE/10GE/25GE RDMA Network Controller
nic_iface=enp125s0f2
nic_mac=b0:4f:a6:2c:b7:62
--------------------------------------
--------------------------------------
nic_pci_addr=7d:00.3
nic_type=Ethernet controller
nic_vendor=Huawei Technologies
nic_model=Co., Ltd. HNS GE/10GE/25GE Network Controller
nic_iface=enp125s0f3
nic_mac=b0:4f:a6:2c:b7:63
--------------------------------------


【扩展硬件信息】

=== 机箱信息 ===
        Manufacturer: Huawei
        Type: Main Server Chassis
        Serial Number: To be filled by O.E.M.
        Asset Tag: To be filled by O.E.M.

=== bios_info ===
bios_vendor=Huawei Corp.
bios_version=6.57
bios_release_date=05/17/2023

=== RAID 控制器 ===
未检测到 RAID 控制器工具(MegaCLI/hpacucli)

=== power_info ===
power_name=PAC900S12-B2
power_manufacturer=HUAWEI
power_serial=2102312XWKW0N2005325
power_max_capacity=900 W

power_name=PAC900S12-B2
power_manufacturer=HUAWEI
power_serial=2102312XWK10N4148986
power_max_capacity=900 W


=== NVMe 设备列表 ===
未安装 nvme-cli 工具

=== 硬盘 WWN ===

=== FC HBA WWN ===
未检测到 FC HBA 卡"
  exit 0
fi

# ========== 判断是否为物理服务器 ==========
if command -v dmidecode &>/dev/null; then
  system_manufacturer=$(sudo dmidecode -s system-manufacturer 2>/dev/null | tr '[:upper:]' '[:lower:]')
  system_product=$(sudo dmidecode -s system-product-name 2>/dev/null | tr '[:upper:]' '[:lower:]')
  
  # 检查是否为虚拟机
  if echo "$system_manufacturer $system_product" | grep -qiE "vmware|virtualbox|qemu|kvm|xen|microsoft.*virtual|parallels|bochs|bhyve"; then
    echo "这是虚拟机"
    exit 0
  fi
fi

# 通过 systemd-detect-virt 二次确认
if command -v systemd-detect-virt &>/dev/null; then
  virt_type=$(systemd-detect-virt 2>/dev/null)
  if [ "$virt_type" != "none" ] && [ -n "$virt_type" ]; then
    echo "这是虚拟机"
    exit 0
  fi
fi

echo -e "\n=== board_info ==="
board_manufacturer=$(sudo dmidecode -t baseboard | awk -F: '/Manufacturer/ {gsub(/^[ \t]+/,"",$2); print $2; exit}')
board_product=$(sudo dmidecode -t baseboard | awk -F: '/Product Name/ {gsub(/^[ \t]+/,"",$2); print $2; exit}')
board_serial=$(sudo dmidecode -t baseboard | awk -F: '/Serial Number/ {gsub(/^[ \t]+/,"",$2); print $2; exit}')

echo "board_manufacturer=${board_manufacturer:-N/A}"
echo "board_product=${board_product:-N/A}"
echo "board_serial=${board_serial:-N/A}"

echo -e "\n=== system_sn ==="
system_sn=$(sudo dmidecode -s system-serial-number)
echo "system_sn=${system_sn:-N/A}"

echo -e "\n=== CPU_info ==="

if command -v lscpu &> /dev/null; then
  arch=$(LC_ALL=C lscpu | awk -F: '/Architecture/ {print $2}' | xargs)
  vendor=$(LC_ALL=C lscpu | awk -F: '/Vendor ID/ {print $2}' | xargs)
  model_name=$(LC_ALL=C lscpu | awk -F: '/Model name/ {print $2}' | xargs)
  cores_per_socket=$(LC_ALL=C lscpu | awk -F: '/Core\(s\) per socket/ {print $2}' | xargs)
  threads_per_core=$(LC_ALL=C lscpu | awk -F: '/Thread\(s\) per core/ {print $2}' | xargs)
  sockets=$(LC_ALL=C lscpu | awk -F: '/Socket\(s\)/ {print $2}' | xargs)
  virtualization=$(LC_ALL=C lscpu | awk -F: '/Virtualization/ {print $2}' | xargs)
  mhz_max=$(LC_ALL=C lscpu | awk -F: '/CPU max MHz/ {print $2}' | xargs)
  mhz_min=$(LC_ALL=C lscpu | awk -F: '/CPU min MHz/ {print $2}' | xargs)

  total_cores=$((cores_per_socket * sockets))
  total_threads=$((total_cores * threads_per_core))

  echo "cpu_arch=${arch:-N/A}"
  echo "cpu_vendor=${vendor:-N/A}"
  echo "cpu_model=${model_name:-N/A}"
  echo "cpu_cores=${total_cores:-N/A}"
  echo "cpu_threads=${total_threads:-N/A}"
  echo "cpu_virtualization=${virtualization:-N/A}"
  echo "cpu_mhz_min=${mhz_min:-N/A}"
  echo "cpu_mhz_max=${mhz_max:-N/A}"
else
  echo "未检测到 lscpu 命令,请先安装 util-linux 包。"
fi


echo -e "\n=== disk_info ==="

# 仅取物理盘(排除 loop / ram 等)
for disk in $(lsblk -d -n -o NAME,TYPE | awk '$2=="disk"{print $1}'); do
  dev="/dev/$disk"

  # 基础信息从 lsblk 获取
  model=$(lsblk -d -n -o MODEL "$dev" 2>/dev/null | xargs)
  vendor=$(lsblk -d -n -o VENDOR "$dev" 2>/dev/null | xargs)
  size=$(lsblk -d -n -o SIZE "$dev" 2>/dev/null | xargs)
  rota=$(lsblk -d -n -o ROTA "$dev" 2>/dev/null | xargs)   # 1=HDD, 0=SSD
  tran=$(lsblk -d -n -o TRAN "$dev" 2>/dev/null | xargs)   # 接口类型: sata/nvme/scsi/...
  [ -z "$tran" ] && tran="N/A"

  if [ "$rota" = "0" ]; then
    media_type="SSD"
  elif [ "$rota" = "1" ]; then
    media_type="HDD"
  else
    media_type="Unknown"
  fi

  # ========== 序列号多级兜底 ==========
  serial=""

  # 1. 对 NVMe 优先用 nvme-cli
  if [[ "$disk" == nvme* ]] && command -v nvme &>/dev/null; then
    serial=$(sudo nvme id-ctrl "$dev" 2>/dev/null | awk -F: '/^sn/ {gsub(/^[ \t]+/,"",$2); print $2}')
    [ -z "$model" ] && model=$(sudo nvme id-ctrl "$dev" 2>/dev/null | awk -F: '/^mn/ {gsub(/^[ \t]+/,"",$2); print $2}')
  fi

  # 2. 普通 SATA/SAS 尝试 hdparm
  if [ -z "$serial" ] && command -v hdparm &>/dev/null; then
    serial=$(sudo hdparm -I "$dev" 2>/dev/null | awk -F':' '/Serial Number/ {gsub(/^[ \t]+/,"",$2); print $2}')
  fi

  # 3. smartctl 兜底
  if [ -z "$serial" ] && command -v smartctl &>/dev/null; then
    serial=$(sudo smartctl -i "$dev" 2>/dev/null | awk -F':' '/Serial Number/ {gsub(/^[ \t]+/,"",$2); print $2}')
  fi

  # 4. 再从 lsblk 的 SERIAL 列兜底
  if [ -z "$serial" ]; then
    serial=$(lsblk -d -n -o SERIAL "$dev" 2>/dev/null | xargs)
  fi

  [ -z "$serial" ] && serial="N/A"
  [ -z "$vendor" ] && vendor="N/A"
  [ -z "$model" ] && model="N/A"
  [ -z "$size" ] && size="N/A"

  echo "disk_name=$dev"
  echo "disk_vendor=$vendor"
  echo "disk_model=$model"
  echo "disk_size=$size"
  echo "disk_tran=$tran"
  echo "disk_type=$media_type"
  echo "disk_sn=$serial"
  echo ""
done

echo -e "\n=== mem_info ==="
if command -v dmidecode &>/dev/null; then
  sudo dmidecode -t memory 2>/dev/null | awk '
    /Memory Device/ {
      # 新的 Memory Device 开始,先把上一个打印出来(如果有效)
      if (seen && size != "" && size !~ /No Module Installed/) {
        printf "mem_locator=%s\n", slot
        printf "mem_manufacturer=%s\n", manu
        printf "mem_part_number=%s\n", part
        printf "mem_type=%s\n", type
        printf "mem_size=%s\n", size
        printf "mem_sn=%s\n", sn
        print ""
      }
      # 重置当前块信息
      seen=1; slot=""; size=""; type=""; manu=""; part=""; sn="";
      next
    }
    seen {
      if ($0 ~ /Locator:/ && $0 !~ /Bank Locator/) {
        sub(/.*Locator:[ \t]*/, "", $0); slot=$0
      } else if ($0 ~ /Size:/) {
        sub(/.*Size:[ \t]*/, "", $0); size=$0
      } else if ($0 ~ /Type:/ && $0 !~ /Error/) {
        sub(/.*Type:[ \t]*/, "", $0); type=$0
      } else if ($0 ~ /Manufacturer:/) {
        sub(/.*Manufacturer:[ \t]*/, "", $0); manu=$0
      } else if ($0 ~ /Part Number:/) {
        sub(/.*Part Number:[ \t]*/, "", $0); part=$0
      } else if ($0 ~ /Serial Number:/) {
        sub(/.*Serial Number:[ \t]*/, "", $0); sn=$0
      }
    }
    END {
      # 打印最后一个有效的 Memory Device
      if (seen && size != "" && size !~ /No Module Installed/) {
        printf "mem_locator=%s\n", slot
        printf "mem_manufacturer=%s\n", manu
        printf "mem_part_number=%s\n", part
        printf "mem_type=%s\n", type
        printf "mem_size=%s\n", size
        printf "mem_sn=%s\n", sn
        print ""
      }
    }'
else
  echo "未安装 dmidecode,无法获取内存信息"
fi

echo -e "\n=== GPU info ==="
# 判断是否安装了 NVIDIA 驱动
if command -v nvidia-smi &> /dev/null; then
  nvidia-smi --query-gpu=index,name,serial,uuid --format=csv,noheader | while IFS=',' read -r index name serial uuid; do
    echo "gpu_index=$(echo "$index" | xargs)"
    echo "gpu_name=$(echo "$name" | xargs)"
    echo "gpu_serial=$(echo "$serial" | xargs)"
    echo "gpu_uuid=$(echo "$uuid" | xargs)"
    echo ""
  done
else
  lspci | grep -iE "vga|3d|display" | while read -r line; do
    pci_addr=$(echo "$line" | awk '{print $1}')
    type=$(echo "$line" | sed -E 's/^[^ ]+ +([^:]+):.*/\1/' | xargs)
    desc=$(echo "$line" | cut -d':' -f3- | sed 's/(rev.*)//' | xargs)
    
    echo "gpu_pci_addr=$pci_addr"
    echo "gpu_type=$type"
    echo "gpu_desc=$desc"
    echo ""
  done
fi


echo -e "\n=== NIC info ==="


if ! command -v lspci &>/dev/null; then
  echo "未检测到 lspci 命令,请先安装 pciutils。"
else
  lspci | grep -Ei "ethernet|network|fibre|infiniband" | while read -r line; do
    pci_addr=$(echo "$line" | awk '{print $1}')

    # 提取类型 (第二列起直到第一个冒号)
    dev_type=$(echo "$line" | sed -E 's/^[^ ]+ +([^:]+):.*/\1/' | xargs)

    # 去掉前缀 "<PCI> TYPE: ",提取厂商+型号
    rest=$(echo "$line" | sed -E 's/^[^ ]+ +[^:]+:[[:space:]]+//')

    # 厂商与型号拆分
    w1=$(echo "$rest" | awk '{print $1}')
    w2=$(echo "$rest" | awk '{print $2}')
    vendor="$w1"
    model=$(echo "$rest" | cut -d' ' -f2-)

    case "$w2" in
      Corporation|Inc|Inc.|Limited|Ltd.|Technologies|Company)
        vendor="$w1 $w2"
        model=$(echo "$rest" | cut -d' ' -f3-)
        ;;
    esac

    model=$(echo "$model" | sed 's/(rev[^)]*)//I' | xargs)

    # 网卡接口与 MAC
    if [ -d "/sys/bus/pci/devices/0000:$pci_addr/net" ]; then
      for n in /sys/bus/pci/devices/0000:$pci_addr/net/*; do
        [ -e "$n" ] || continue
        iface=$(basename "$n")
        mac=$(cat "/sys/class/net/$iface/address" 2>/dev/null)

        echo "--------------------------------------"
        echo "nic_pci_addr=$pci_addr"
        echo "nic_type=$dev_type"
        echo "nic_vendor=$vendor"
        echo "nic_model=$model"
        echo "nic_iface=$iface"
        echo "nic_mac=${mac:-N/A}"
        echo "--------------------------------------"
      done
    else
      echo "--------------------------------------"
      echo "nic_pci_addr=$pci_addr"
      echo "nic_type=$dev_type"
      echo "nic_vendor=$vendor"
      echo "nic_model=$model"
      echo "nic_iface=N/A"
      echo "nic_mac=N/A"
      echo "--------------------------------------"
    fi
  done
fi
# ============ 扩展信息 ============
echo -e "\n\n【扩展硬件信息】"

echo -e "\n=== 机箱信息 ==="
sudo dmidecode -t chassis | grep -E "Manufacturer|Type|Serial Number|Asset Tag"

echo -e "\n=== bios_info ==="
if command -v dmidecode &>/dev/null; then
  bios_vendor=$(sudo dmidecode -t 0 2>/dev/null | awk -F: '/Vendor:/ {gsub(/^[ \t]+/,"",$2); print $2; exit}')
  bios_version=$(sudo dmidecode -t 0 2>/dev/null | awk -F: '/Version:/ {gsub(/^[ \t]+/,"",$2); print $2; exit}')
  bios_release_date=$(sudo dmidecode -t 0 2>/dev/null | awk -F: '/Release Date:/ {gsub(/^[ \t]+/,"",$2); print $2; exit}')
  
  echo "bios_vendor=${bios_vendor:-N/A}"
  echo "bios_version=${bios_version:-N/A}"
  echo "bios_release_date=${bios_release_date:-N/A}"
else
  echo "未安装 dmidecode,无法获取 BIOS 信息"
fi

echo -e "\n=== RAID 控制器 ==="
if command -v megacli &> /dev/null; then
  sudo megacli -AdpAllInfo -aAll 2>/dev/null | grep -E "Product Name|Serial No"
elif command -v hpacucli &> /dev/null; then
  sudo hpacucli ctrl all show detail 2>/dev/null | grep -E "Serial Number|Model"
else
  echo "未检测到 RAID 控制器工具(MegaCLI/hpacucli)"
fi

echo -e "\n=== power_info ==="
if command -v dmidecode &>/dev/null; then
  sudo dmidecode -t 39 2>/dev/null | awk '
    /Power Supply/ {
      # 新的 Power Supply 开始,先把上一个打印出来(如果有效)
      if (seen && (name != "" || manu != "" || sn != "" || capacity != "")) {
        printf "power_name=%s\n", name
        printf "power_manufacturer=%s\n", manu
        printf "power_serial=%s\n", sn
        printf "power_max_capacity=%s\n", capacity
        print ""
      }
      # 重置当前块信息
      seen=1; name=""; manu=""; sn=""; capacity="";
      next
    }
    seen {
      if ($0 ~ /Name:/) {
        sub(/.*Name:[ \t]*/, "", $0); name=$0
      } else if ($0 ~ /Manufacturer:/) {
        sub(/.*Manufacturer:[ \t]*/, "", $0); manu=$0
      } else if ($0 ~ /Serial Number:/) {
        sub(/.*Serial Number:[ \t]*/, "", $0); sn=$0
      } else if ($0 ~ /Max Power Capacity:/) {
        sub(/.*Max Power Capacity:[ \t]*/, "", $0); capacity=$0
      }
    }
    END {
      # 打印最后一个有效的 Power Supply
      if (seen && (name != "" || manu != "" || sn != "" || capacity != "")) {
        printf "power_name=%s\n", name
        printf "power_manufacturer=%s\n", manu
        printf "power_serial=%s\n", sn
        printf "power_max_capacity=%s\n", capacity
        print ""
      }
    }'
else
  echo "未安装 dmidecode,无法获取电源信息"
fi

echo -e "\n=== NVMe 设备列表 ==="
if command -v nvme &> /dev/null; then
  sudo nvme list 2>/dev/null
else
  echo "未安装 nvme-cli 工具"
fi

echo -e "\n=== 硬盘 WWN ==="
for disk in $(lsblk -d -n -o NAME,TYPE | awk '$2=="disk"{print $1}'); do
  dev="/dev/$disk"
  wwn=$(sudo smartctl -i "$dev" 2>/dev/null | awk '/LU WWN Device Id:/ {print $4$5$6$7}')
  if [ -n "$wwn" ]; then
    echo "$dev: $wwn"
  fi
done

echo -e "\n=== FC HBA WWN ==="
if [ -d /sys/class/fc_host ]; then
  for host in /sys/class/fc_host/host*; do
    echo "$(basename "$host"): WWPN=$(cat "$host/port_name") WWNN=$(cat "$host/node_name")"
  done
else
  echo "未检测到 FC HBA 卡"
fi


