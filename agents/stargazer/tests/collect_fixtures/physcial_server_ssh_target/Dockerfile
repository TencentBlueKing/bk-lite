FROM docker.m.daocloud.io/library/ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# 构建时走 host 网络（见 compose build.network），避免 Docker bridge 访问 Ubuntu 源超时。
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      openssh-server sudo iproute2 curl pciutils dmidecode \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /run/sshd

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22
CMD ["bash", "/entrypoint.sh"]
