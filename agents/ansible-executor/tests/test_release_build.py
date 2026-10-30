import argparse
import io
import json
import tarfile
from unittest.mock import patch

import pytest

import build_release as builder
from release_policy import sha256


def fixture(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    (source / ".venv").mkdir()
    (source / ".venv/keep").write_text("original")
    cache = tmp_path / "archives"
    cache.mkdir()
    with tarfile.open(cache / "openssl-3.5.9.tar.gz", "w:gz") as archive:
        data = b"#!/bin/sh\n"
        info = tarfile.TarInfo("openssl-3.5.9/Configure")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    (cache / "cryptography-46.0.5.tar.gz").write_bytes(b"fixture source")
    lock = {
        name: {"filename": filename, "sha256": sha256(cache / filename)}
        for name, filename in [("openssl", "openssl-3.5.9.tar.gz"), ("cryptography", "cryptography-46.0.5.tar.gz")]
    }
    (source / "release-sources.json").write_text(json.dumps(lock))
    args = argparse.Namespace(work_dir=tmp_path / "work", dist_dir=tmp_path / "dist", python="/fixture/python", uv="uv", sources_dir=cache)
    return source, args


@pytest.mark.parametrize("fail_at", [None, "wheel", "freeze"])
def test_isolated_build_and_failure_do_not_publish_partial_package(tmp_path, fail_at):
    source, args = fixture(tmp_path)
    commands = []

    def execute(argv, cwd, env):
        argv = list(map(str, argv))
        commands.append(argv)
        assert env["UV_PROJECT_ENVIRONMENT"] == str(args.work_dir / "venv")
        if argv[:2] == ["uv", "build"]:
            assert env["OPENSSL_STATIC"] == "1"
            assert env["OPENSSL_DIR"] == str(args.work_dir / "openssl")
            assert env["CARGO_BUILD_JOBS"] == "2"
            wheelhouse = args.work_dir / "wheelhouse"
            wheelhouse.mkdir()
            if fail_at != "wheel":
                (wheelhouse / "cryptography-46.0.5-fixture.whl").write_bytes(b"wheel")
        if "PyInstaller" in argv:
            if fail_at == "freeze":
                raise RuntimeError("frozen runtime rejected")
            candidate = args.work_dir / "candidate/ansible-executor"
            candidate.mkdir(parents=True)
            (candidate / "ansible-executor").write_bytes(b"verified fixture")

    with (
        patch.object(builder, "SOURCE", source),
        patch.object(builder.platform, "system", return_value="Linux"),
        patch.object(builder.platform, "machine", return_value="x86_64"),
        patch.object(builder.subprocess, "check_output", return_value='["3.12.15", "3.5.9"]'),
        patch.object(builder, "run", side_effect=execute),
    ):
        if fail_at:
            with pytest.raises(RuntimeError):
                builder.build(args)
            assert not (args.dist_dir / "ansible-executor").exists()
        else:
            builder.build(args)
            assert (args.dist_dir / "ansible-executor/ansible-executor").read_bytes() == b"verified fixture"
            sync = next(i for i, c in enumerate(commands) if c[:2] == ["uv", "sync"])
            custom = next(i for i, c in enumerate(commands) if "--reinstall-package" in c)
            freeze = next(i for i, c in enumerate(commands) if "PyInstaller" in c)
            assert sync < custom < freeze
    assert (source / ".venv/keep").read_text() == "original"
    assert not (args.work_dir / "source/.venv").exists()


@pytest.mark.parametrize("case", ["architecture", "nested-work", "existing-dist", "wrong-python", "existing-work"])
def test_build_preflight_rejects_unsafe_or_unsupported_inputs(tmp_path, case):
    source, args = fixture(tmp_path)
    if case == "nested-work":
        args.work_dir = source / "work"
    if case == "existing-dist":
        (args.dist_dir / "ansible-executor").mkdir(parents=True)
        (args.dist_dir / "ansible-executor/keep").write_text("original")
    if case == "existing-work":
        args.work_dir.mkdir()
    runtime = '["3.12.13", "3.5.7"]' if case == "wrong-python" else '["3.12.15", "3.5.9"]'
    with (
        patch.object(builder, "SOURCE", source),
        patch.object(builder.platform, "system", return_value="Linux"),
        patch.object(builder.platform, "machine", return_value="aarch64" if case == "architecture" else "x86_64"),
        patch.object(builder.subprocess, "check_output", return_value=runtime),
        patch.object(builder, "run") as execute,
    ):
        with pytest.raises((RuntimeError, FileExistsError)):
            builder.build(args)
        execute.assert_not_called()
    if case == "existing-dist":
        assert (args.dist_dir / "ansible-executor/keep").read_text() == "original"


def test_network_source_is_verified(tmp_path):
    content = b"upstream fixture"
    path = tmp_path / "source"
    path.write_bytes(content)
    item = {"filename": "source", "url": "https://example.invalid/source", "sha256": sha256(path)}
    with patch.object(builder.urllib.request, "urlopen", return_value=io.BytesIO(content)):
        assert builder.source_archive(item, tmp_path).read_bytes() == content


def test_subprocess_is_bounded_and_failure_propagates(tmp_path):
    import subprocess

    error = subprocess.CalledProcessError(1, "make")
    with patch.object(builder.subprocess, "run", side_effect=error) as execute:
        with pytest.raises(subprocess.CalledProcessError) as caught:
            builder.run(["make"], tmp_path, {})
    assert caught.value is error
    assert execute.call_args.kwargs["timeout"] == 1800
    assert execute.call_args.kwargs["check"] is True
