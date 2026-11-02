#!/bin/sh
# Jenkins 构建节点执行；只构建独立候选镜像，不推送、不修改运行容器。
set -eu
: "${BASE_IMAGE:?必须提供原环境镜像摘要}"
: "${CANDIDATE_IMAGE:?必须提供独立候选标签}"
case "$BASE_IMAGE" in *@sha256:*) ;; *) echo '基础镜像必须固定摘要' >&2; exit 1 ;; esac
case "$CANDIDATE_IMAGE" in *:latest|"$BASE_IMAGE"|-*) echo '禁止覆盖 latest 或原镜像' >&2; exit 1 ;; esac
case "${CANDIDATE_IMAGE##*/}" in
    *:latest|*:) echo '候选镜像必须使用本次发布的非 latest 标签' >&2; exit 1 ;;
    *:*) ;;
    *) echo '候选镜像必须显式指定标签' >&2; exit 1 ;;
esac
security_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
docker pull "$BASE_IMAGE"
runtime_user=$(docker image inspect --format '{{.Config.User}}' "$BASE_IMAGE")
docker build --pull --no-cache \
    --build-arg BASE_IMAGE="$BASE_IMAGE" --build-arg RUNTIME_USER="${runtime_user:-0}" \
    -f "$security_dir/Dockerfile.falkordb" -t "$CANDIDATE_IMAGE" "$security_dir"
for field in User Entrypoint Cmd; do
    before=$(docker image inspect --format "{{json .Config.$field}}" "$BASE_IMAGE")
    after=$(docker image inspect --format "{{json .Config.$field}}" "$CANDIDATE_IMAGE")
    if [ "$field" = User ] && [ "$before" = '""' ]; then before='"0"'; fi
    test "$before" = "$after"
done
python3 "$security_dir/brotli_release.py" check-image --profile node-system --image "$CANDIDATE_IMAGE"
