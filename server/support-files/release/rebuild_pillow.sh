#!/bin/sh
# CVE-2026-111497：预编译 Pillow wheel 自带 Brotli，不受系统 libbrotli 更新影响。
# 保留应用原有 Pillow 版本，从源码重建，改用发行版维护的 FreeType / Brotli。
set -eu

python=${PYTHON:-python3}
pillow_version=$("$python" -c 'from importlib.metadata import version; print(version("Pillow"))')
apt-get update
apt-get install -y --no-install-recommends \
    build-essential pkg-config libbrotli1 libfreetype6-dev \
    libjpeg62-turbo-dev zlib1g-dev libtiff-dev liblcms2-dev \
    libwebp-dev libopenjp2-7-dev libraqm-dev libxcb1-dev libavif-dev
"$python" -m pip install --no-cache-dir --force-reinstall --no-deps \
    --no-binary=pillow "pillow==$pillow_version"
rm -rf /var/lib/apt/lists/*
