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
