// 插入现有流水线 stages：应用镜像构建之后，发布部署之前。
// 这是 review 用的阶段片段，不是对线上 Jenkins 的自动修改。
stage('构建并验收 Brotli 修复镜像') {
    options { timeout(time: 30, unit: 'MINUTES') }
    steps {
        sh '''
            set -eu
            # 两个基础镜像分别取自实际生产、开发环境，须使用 @sha256 摘要。
            : "${FALKORDB_BASE_IMAGE:?}"
            : "${DEV_FALKORDB_BASE_IMAGE:?}"
            : "${FALKORDB_CANDIDATE_IMAGE:?本次构建唯一标签}"
            : "${DEV_FALKORDB_CANDIDATE_IMAGE:?本次构建唯一标签}"
            : "${LICENSE_IMAGE:?授权服务已升级的镜像摘要}"
            : "${FUSION_IMAGE:?重新构建的 Fusion 最终发行镜像}"
            test "$FALKORDB_CANDIDATE_IMAGE" != "$DEV_FALKORDB_CANDIDATE_IMAGE"
            BASE_IMAGE="$FALKORDB_BASE_IMAGE" CANDIDATE_IMAGE="$FALKORDB_CANDIDATE_IMAGE" \
                sh deploy/security/build_falkordb.sh
            BASE_IMAGE="$DEV_FALKORDB_BASE_IMAGE" CANDIDATE_IMAGE="$DEV_FALKORDB_CANDIDATE_IMAGE" \
                sh deploy/security/build_falkordb.sh
            # 授权服务没有本仓库构建入口：必须由其仓库重建后提供，旧 Node 会阻断发布。
            case "$LICENSE_IMAGE" in *@sha256:*) ;; *) echo "授权服务须提供镜像摘要" >&2; exit 1 ;; esac
            docker pull "$LICENSE_IMAGE"
            python3 deploy/security/brotli_release.py check-image --image "$LICENSE_IMAGE" --profile node
            python3 deploy/security/brotli_release.py check-image --image "$FUSION_IMAGE" --profile system
            # 全部版本检查通过后，再接现有 registry 凭据管理下的 push 流程。
            # docker push "$FALKORDB_CANDIDATE_IMAGE"
            # docker push "$DEV_FALKORDB_CANDIDATE_IMAGE"
        '''
    }
}
