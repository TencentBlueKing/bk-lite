from pathlib import Path

STARGAZER_ROOT = Path(__file__).resolve().parents[1]


def test_stargazer_image_uses_verified_enterprise_submodule_context():
    makefile = (STARGAZER_ROOT / "Makefile").read_text(encoding="utf-8")
    dockerfile = (STARGAZER_ROOT / "support-files/docker/Dockerfile").read_text(encoding="utf-8")
    dockerignore = (STARGAZER_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert "git -C ../.. ls-tree HEAD -- enterprise" in makefile
    assert "git -C ../../enterprise rev-parse HEAD" in makefile
    assert 'actual_enterprise_sha" != "$$expected_enterprise_sha' in makefile
    assert "--build-context enterprise_src=../../enterprise/agents/stargazer/enterprise" in makefile
    assert '--build-arg ENTERPRISE_SHA="$$expected_enterprise_sha"' in makefile

    assert "COPY --from=enterprise_src . ./enterprise" in dockerfile
    assert 'test -n "$ENTERPRISE_SHA"' in dockerfile
    assert "enterprise.plugins.inputs.sangforhci.sangforhci_info" in dockerfile
    assert "enterprise.plugins.inputs.sangforscp.sangforscp_info" in dockerfile
    assert "enterprise" in dockerignore
