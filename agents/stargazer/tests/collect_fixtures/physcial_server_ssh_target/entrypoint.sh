#!/bin/bash
# 复用 collect_fixtures SSH bootstrap：sshd + root/testpw，并装 pciutils/dmidecode。
# privileged 下若宿主机有 PCI/virtio 网卡，discover 脚本可扫到真实 NIC。
# 若 /sys/bus/pci 下没有任何 net iface，则种一张稳定 MAC 的 QA 网卡，避免两次采集 nic 数为 0。
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
SSH_PASSWORD="${SSH_PASSWORD:-testpw}"

if [ -f /etc/apt/sources.list ]; then
  sed -i 's|//ports.ubuntu.com/ubuntu-ports|//mirrors.aliyun.com/ubuntu-ports|g; s|//archive.ubuntu.com/ubuntu|//mirrors.aliyun.com/ubuntu|g' /etc/apt/sources.list
fi
apt-get update -qq
apt-get install -y -qq openssh-server sudo iproute2 curl pciutils dmidecode >/dev/null

echo "root:${SSH_PASSWORD}" | chpasswd
sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/^#*PermitEmptyPasswords.*/PermitEmptyPasswords no/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/^#*KbdInteractiveAuthentication.*/KbdInteractiveAuthentication no/' /etc/ssh/sshd_config
mkdir -p /run/sshd
ssh-keygen -A >/dev/null 2>&1

seed_pci_nic_if_missing() {
  if ls -d /sys/bus/pci/devices/*/net/* >/dev/null 2>&1; then
    return 0
  fi
  ip link add ethqa type dummy 2>/dev/null || true
  ip link set ethqa address 0a:00:00:00:00:01 2>/dev/null || true
  ip link set ethqa up 2>/dev/null || true

  qa_pci="0000:00:03.0"
  qa_bus="/run/qa-pci-bus"
  mkdir -p "${qa_bus}/${qa_pci}/net/ethqa"

  if [ -d /sys/bus/pci/devices ]; then
    if [ -z "$(ls -A /sys/bus/pci/devices 2>/dev/null || true)" ]; then
      mount --bind "${qa_bus}" /sys/bus/pci/devices 2>/dev/null || true
    fi
  fi

  real_lspci="/usr/bin/lspci"
  cat > /usr/local/sbin/lspci <<'EOF'
#!/bin/bash
real=/usr/bin/lspci
if [ -x "$real" ]; then
  "$real" "$@"
fi
if ! { [ -x "$real" ] && "$real" | grep -qiE 'ethernet|network|fibre|infiniband'; }; then
  echo "00:03.0 Ethernet controller: QA Dummy NIC"
fi
EOF
  chmod +x /usr/local/sbin/lspci
}

seed_pci_nic_if_missing

exec /usr/sbin/sshd -D
