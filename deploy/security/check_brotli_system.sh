#!/bin/sh
# 只读检查；发行版回补补丁以完整软件包版本为准。
set -eu
. /etc/os-release
case "$ID:$VERSION_ID" in
  debian:12) minimum='1.0.9-2+deb12u1' ;;
  debian:13) minimum='1.1.0-2+deb13u1' ;;
  ubuntu:20.04) minimum='1.0.7-6ubuntu0.1+esm1' ;;
  ubuntu:22.04) minimum='1.0.9-2ubuntu0.1' ;;
  ubuntu:24.04) minimum='1.1.0-2ubuntu0.1' ;;
  *) echo '未验证的系统 Brotli 发行版' >&2; exit 1 ;;
esac
dpkg-query -W -f='${db:Status-Abbrev}' libbrotli1 | grep -q '^ii '
version=$(dpkg-query -W -f='${Version}' libbrotli1)
dpkg --compare-versions "$version" ge "$minimum"
printf 'libbrotli1 %s\n' "$version"
