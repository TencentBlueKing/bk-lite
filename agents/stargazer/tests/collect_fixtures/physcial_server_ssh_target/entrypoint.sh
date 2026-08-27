#!/bin/bash
# 镜像构建阶段已安装 sshd/pciutils；此处只配账户、种 QA 网卡、前台跑 sshd。
set -euo pipefail
SSH_PASSWORD="${SSH_PASSWORD:-testpw}"

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
  ip link add ethqa type dummy 2>/dev/null \
    || ip link add name ethqa type veth peer name ethqa-p 2>/dev/null \
    || true
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
