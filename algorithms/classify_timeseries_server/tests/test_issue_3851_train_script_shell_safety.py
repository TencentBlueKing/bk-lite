import os
import subprocess
from pathlib import Path


def test_train_script_does_not_reparse_arguments_with_eval():
    service_root = Path(__file__).resolve().parents[1]
    script = service_root / "support-files" / "scripts" / "train-model.sh"
    text = script.read_text()

    assert "eval ${TRAIN_CMD}" not in text
    assert 'TRAIN_CMD="' not in text
    assert '$(basename -- "${DATASET_NAME}")' in text
    assert '$(basename -- "${CONFIG_NAME}")' in text
    assert f"{service_root.name} train" in text
    assert '"${TRAIN_CMD[@]}"' in text

    subprocess.run(["bash", "-n", str(script)], check=True)


def test_train_script_passes_shell_fragments_as_literal_arguments(tmp_path, monkeypatch):
    service_root = Path(__file__).resolve().parents[1]
    script = service_root / "support-files" / "scripts" / "train-model.sh"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    for name, body in {
        "python": 'out=""; while [ "$#" -gt 0 ]; do case "$1" in --output) shift; out="$1";; esac; shift; done; mkdir -p "$(dirname "$out")"; printf stub > "$out"\n',
        "unzip": 'dest=""; while [ "$#" -gt 0 ]; do case "$1" in -d) shift; dest="$1";; esac; shift; done; mkdir -p "$dest"\n',
        service_root.name: 'printf "%s\\n" "$@" > "$CALLS_FILE"\n',
    }.items():
        path = fake_bin / name
        path.write_text(f"#!/bin/bash\nset -e\n{body}")
        path.chmod(0o755)

    calls_file = tmp_path / "calls"
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    monkeypatch.setenv("CALLS_FILE", str(calls_file))
    monkeypatch.setenv("DOWNLOAD_DIR", str(tmp_path / "downloads"))
    monkeypatch.setenv("EXTRACT_DIR", str(tmp_path / "datasets"))
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "configs"))
    monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "ak")
    monkeypatch.setenv("MINIO_SECRET_KEY", "sk")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://mlflow")

    malicious_config = "$(:>pwned).json"
    subprocess.run(["bash", str(script), "bucket", "data.zip", malicious_config], cwd=tmp_path, check=True)

    assert not (tmp_path / "pwned").exists()
    assert malicious_config in calls_file.read_text()
