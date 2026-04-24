from pathlib import Path


def test_k8s_render_support_templates_are_packaged_together():
    support_dir = Path(__file__).resolve().parents[1] / "support-files" / "kubernetes-event-exporter"
    secret_template = support_dir / "secret.yaml.template"
    exporter_template = support_dir / "bk-lite-k8s-event-exporter.yaml"

    assert secret_template.is_file()
    assert exporter_template.is_file()

    secret_content = secret_template.read_text(encoding="utf-8")
    exporter_content = exporter_template.read_text(encoding="utf-8")

    assert "kind: Secret" in secret_content
    assert "your-k8s-cluster" in secret_content
    assert "http://bk-lite-server:8001/api/v1/alerts/api/receiver_data/" in secret_content
    assert "your-alert-source-secret" in secret_content
    assert "BK_LITE_PUSH_SOURCE_ID: k8s" in secret_content
    assert "kind: Deployment" in exporter_content
    assert "name: kubernetes-event-exporter" in exporter_content
