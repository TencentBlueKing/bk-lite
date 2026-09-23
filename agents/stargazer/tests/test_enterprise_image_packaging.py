from pathlib import Path

STARGAZER_ROOT = Path(__file__).resolve().parents[1]


def _makefile_recipe(makefile: str, target: str) -> str:
    lines = makefile.splitlines()
    header = f"{target}:"
    start = next(index for index, line in enumerate(lines) if line.startswith(header))
    end = start + 1
    while end < len(lines) and (not lines[end] or lines[end][:1] in {" ", "\t"}):
        end += 1
    return "\n".join(lines[start:end])


def test_community_build_target_does_not_require_enterprise():
    dockerfile = (STARGAZER_ROOT / "support-files/docker/Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.startswith("FROM python:3.12 AS community\n")
    community, enterprise = dockerfile.split("FROM community AS enterprise\n", 1)

    assert "enterprise_src" not in community
    assert "ENTERPRISE_SHA" not in community
    assert "import enterprise." not in community
    assert 'RUN pip3 install -e ".[dev,aliyun,qcloud,huawei,vmware,openstack,qingyun,snmp]"' in community
    assert 'CMD ["supervisord", "-n"]' in community

    # 最后一阶段仍为企业版，兼容现有不带 --target 的企业版流水线。
    assert "FROM " not in enterprise
    assert "COPY --from=enterprise_src . ./enterprise" in enterprise
    assert 'test -n "$ENTERPRISE_SHA"' in enterprise
    assert "import enterprise.plugins.inputs.sangforhci.sangforhci_info" in enterprise
    assert "import enterprise.plugins.inputs.sangforscp.sangforscp_info" in enterprise


def test_community_make_build_does_not_require_enterprise():
    makefile = (STARGAZER_ROOT / "Makefile").read_text(encoding="utf-8")
    community_build = _makefile_recipe(makefile, "build")

    assert "--target community" in community_build
    assert "ls-tree HEAD -- enterprise" not in community_build
    assert "enterprise_src" not in community_build
    assert "ENTERPRISE_SHA" not in community_build


def test_stargazer_image_uses_verified_enterprise_submodule_context():
    makefile = (STARGAZER_ROOT / "Makefile").read_text(encoding="utf-8")
    dockerfile = (STARGAZER_ROOT / "support-files/docker/Dockerfile").read_text(encoding="utf-8")
    dockerignore = (STARGAZER_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    enterprise_build = _makefile_recipe(makefile, "build-enterprise")

    assert "git -C ../.. ls-tree HEAD -- enterprise" in enterprise_build
    assert "git -C ../../enterprise rev-parse HEAD" in enterprise_build
    assert 'actual_enterprise_sha" != "$$expected_enterprise_sha' in enterprise_build
    assert "--build-context enterprise_src=../../enterprise/agents/stargazer/enterprise" in enterprise_build
    assert "--build-arg ENTERPRISE_SHA=\"$$expected_enterprise_sha\"" in enterprise_build
    assert "-t bklite/stargazer-enterprise" in enterprise_build
    assert "--target community" not in enterprise_build

    assert "COPY --from=enterprise_src . ./enterprise" in dockerfile
    assert 'test -n "$ENTERPRISE_SHA"' in dockerfile
    assert "enterprise.plugins.inputs.sangforhci.sangforhci_info" in dockerfile
    assert "enterprise.plugins.inputs.sangforscp.sangforscp_info" in dockerfile
    assert "enterprise" in dockerignore
