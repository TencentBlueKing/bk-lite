from pathlib import Path

import yaml


MANIFEST_PATH = Path(__file__).resolve().parents[2] / "bk-lite-k3s-metric-collector.yaml"
NAMESPACE = "bk-lite-k3s-collector"
KSM_METRICS = {
    "kube_daemonset_status_desired_number_scheduled",
    "kube_daemonset_status_number_available",
    "kube_daemonset_status_number_unavailable",
    "kube_deployment_spec_replicas",
    "kube_deployment_status_replicas_available",
    "kube_deployment_status_replicas_unavailable",
    "kube_node_info",
    "kube_node_status_allocatable",
    "kube_node_status_condition",
    "kube_pod_container_resource_limits",
    "kube_pod_container_resource_requests",
    "kube_pod_container_status_restarts_total",
    "kube_pod_container_status_waiting_reason",
    "kube_pod_info",
    "kube_pod_status_phase",
    "kube_statefulset_replicas",
    "kube_statefulset_status_replicas_ready",
}


def _load_documents():
    return [document for document in yaml.safe_load_all(MANIFEST_PATH.read_text(encoding="utf-8")) if document]


def _find_document(documents, kind, name):
    return next(
        document
        for document in documents
        if document["kind"] == kind and document["metadata"]["name"] == name
    )


def test_k3s_manifest_is_independent_and_does_not_deploy_docker_cadvisor():
    documents = _load_documents()
    identities = {(document["kind"], document["metadata"]["name"]) for document in documents}

    assert ("Namespace", NAMESPACE) in identities
    assert ("Deployment", "k3s-vmagent") in identities
    assert ("Deployment", "k3s-kube-state-metrics") in identities
    assert ("Deployment", "k3s-metric-telegraf") in identities
    assert ("DaemonSet", "k3s-node-telegraf") in identities

    for document in documents:
        if document["kind"] != "Namespace" and "namespace" in document["metadata"]:
            assert document["metadata"]["namespace"] == NAMESPACE

    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
    assert "bk-lite-collector" not in manifest_text
    assert "--docker_only" not in manifest_text
    assert "/var/lib/docker" not in manifest_text
    assert "docker.sock" not in manifest_text
    assert "\n  name: cadvisor\n" not in manifest_text


def test_vmagent_uses_service_account_tls_and_minimum_node_proxy_rbac():
    documents = _load_documents()
    service_account = _find_document(documents, "ServiceAccount", "k3s-vmagent")
    role = _find_document(documents, "ClusterRole", "bk-lite-k3s-vmagent")
    binding = _find_document(documents, "ClusterRoleBinding", "bk-lite-k3s-vmagent")
    config_map = _find_document(documents, "ConfigMap", "k3s-vmagent-config")
    deployment = _find_document(documents, "Deployment", "k3s-vmagent")

    assert service_account["metadata"]["namespace"] == NAMESPACE
    assert role["rules"] == [
        {
            "apiGroups": [""],
            "resources": ["nodes"],
            "verbs": ["get", "list", "watch"],
        },
        {
            "apiGroups": [""],
            "resources": ["nodes/proxy"],
            "verbs": ["get"],
        },
    ]
    assert binding["roleRef"]["name"] == "bk-lite-k3s-vmagent"
    assert binding["subjects"] == [
        {
            "kind": "ServiceAccount",
            "name": "k3s-vmagent",
            "namespace": NAMESPACE,
        }
    ]
    assert deployment["spec"]["template"]["spec"]["serviceAccountName"] == "k3s-vmagent"

    prometheus_config = config_map["data"]["prometheus.yml"]
    assert "role: node" in prometheus_config
    assert "https" in prometheus_config
    assert "kubernetes.default.svc:443" in prometheus_config
    assert "/api/v1/nodes/$1/proxy/metrics/cadvisor" in prometheus_config
    assert "/var/run/secrets/kubernetes.io/serviceaccount/token" in prometheus_config
    assert "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt" in prometheus_config
    assert "server_name: kubernetes.default.svc" in prometheus_config
    assert "insecure_skip_verify" not in prometheus_config


def test_cadvisor_scrape_keeps_only_the_six_monitoring_metric_families():
    documents = _load_documents()
    config_map = _find_document(documents, "ConfigMap", "k3s-vmagent-config")
    prometheus_config = yaml.safe_load(config_map["data"]["prometheus.yml"])
    cadvisor_job = next(
        job
        for job in prometheus_config["scrape_configs"]
        if job["job_name"] == "k3s-kubelet-cadvisor"
    )

    keep_rules = [
        rule
        for rule in cadvisor_job["metric_relabel_configs"]
        if rule.get("action") == "keep" and rule.get("source_labels") == ["__name__"]
    ]
    assert keep_rules == [
        {
            "source_labels": ["__name__"],
            "action": "keep",
            "regex": (
                "container_cpu_usage_seconds_total|"
                "container_memory_working_set_bytes|"
                "container_fs_reads_total|"
                "container_fs_writes_total|"
                "container_network_receive_bytes_total|"
                "container_network_transmit_bytes_total"
            ),
        }
    ]
    assert {
        "source_labels": ["pod"],
        "regex": "",
        "action": "drop",
    } in cadvisor_job["metric_relabel_configs"]
    assert {
        "regex": "id|image|name",
        "action": "labeldrop",
    } in cadvisor_job["metric_relabel_configs"]


def test_kube_state_metrics_is_k3s_owned_and_exposes_the_dashboard_contract():
    documents = _load_documents()
    service_account = _find_document(documents, "ServiceAccount", "k3s-kube-state-metrics")
    role = _find_document(documents, "ClusterRole", "bk-lite-k3s-kube-state-metrics")
    binding = _find_document(documents, "ClusterRoleBinding", "bk-lite-k3s-kube-state-metrics")
    service = _find_document(documents, "Service", "k3s-kube-state-metrics")
    deployment = _find_document(documents, "Deployment", "k3s-kube-state-metrics")

    assert service_account["metadata"]["namespace"] == NAMESPACE
    assert role["rules"] == [
        {
            "apiGroups": [""],
            "resources": ["nodes", "pods"],
            "verbs": ["list", "watch"],
        },
        {
            "apiGroups": ["apps"],
            "resources": ["daemonsets", "deployments", "statefulsets"],
            "verbs": ["list", "watch"],
        },
    ]
    assert binding["roleRef"]["name"] == "bk-lite-k3s-kube-state-metrics"
    assert binding["subjects"][0]["name"] == "k3s-kube-state-metrics"
    assert binding["subjects"][0]["namespace"] == NAMESPACE
    assert service["spec"]["selector"] == {"app.kubernetes.io/name": "k3s-kube-state-metrics"}

    pod_spec = deployment["spec"]["template"]["spec"]
    assert pod_spec["serviceAccountName"] == "k3s-kube-state-metrics"
    args = pod_spec["containers"][0]["args"]
    assert "--resources=daemonsets,deployments,nodes,pods,statefulsets" in args
    allowlist_arg = next(arg for arg in args if arg.startswith("--metric-allowlist="))
    assert set(allowlist_arg.removeprefix("--metric-allowlist=").split(",")) == KSM_METRICS

    config_map = _find_document(documents, "ConfigMap", "k3s-vmagent-config")
    prometheus_config = yaml.safe_load(config_map["data"]["prometheus.yml"])
    ksm_job = next(
        job
        for job in prometheus_config["scrape_configs"]
        if job["job_name"] == "k3s-kube-state-metrics"
    )
    assert ksm_job["static_configs"] == [{"targets": ["k3s-kube-state-metrics:8080"]}]
    keep_rule = next(
        rule
        for rule in ksm_job["metric_relabel_configs"]
        if rule.get("action") == "keep"
    )
    assert set(keep_rule["regex"].split("|")) == KSM_METRICS


def test_telegraf_receives_remote_write_and_reports_node_metrics_to_nats():
    documents = _load_documents()
    service = _find_document(documents, "Service", "k3s-metric-telegraf")
    metric_config = _find_document(documents, "ConfigMap", "k3s-metric-telegraf-config")
    node_config = _find_document(documents, "ConfigMap", "k3s-node-telegraf-config")
    metric_deployment = _find_document(documents, "Deployment", "k3s-metric-telegraf")
    node_daemonset = _find_document(documents, "DaemonSet", "k3s-node-telegraf")

    assert service["spec"]["selector"] == {"app.kubernetes.io/name": "k3s-metric-telegraf"}
    assert service["spec"]["ports"] == [
        {
            "name": "remote-write",
            "port": 9090,
            "targetPort": "remote-write",
        }
    ]

    metric_toml = metric_config["data"]["telegraf.conf"]
    assert 'service_address = ":9090"' in metric_toml
    assert 'paths = ["/receive"]' in metric_toml
    assert 'data_format = "prometheusremotewrite"' in metric_toml
    assert 'subject = "metrics.cloud"' in metric_toml
    assert "insecure_skip_verify = false" in metric_toml

    node_toml = node_config["data"]["telegraf.conf"]
    for input_name in ("cpu", "disk", "diskio", "mem", "net", "system"):
        assert f"[[inputs.{input_name}]]" in node_toml
    assert 'instance_type = "k3s"' in node_toml
    assert 'instance_id = "${CLUSTER_NAME}"' in node_toml
    assert 'node = "${HOST_NODE_NAME}"' in node_toml
    assert 'subject = "metrics.cloud"' in node_toml
    assert "insecure_skip_verify = false" in node_toml

    metric_pod_spec = metric_deployment["spec"]["template"]["spec"]
    assert metric_deployment["spec"]["replicas"] == 1
    assert metric_pod_spec["containers"][0]["ports"] == [
        {"name": "remote-write", "containerPort": 9090}
    ]

    node_pod_spec = node_daemonset["spec"]["template"]["spec"]
    node_container = node_pod_spec["containers"][0]
    env = {item["name"]: item["value"] for item in node_container["env"] if "value" in item}
    assert env["HOST_PROC"] == "/hostfs/proc"
    assert env["HOST_SYS"] == "/hostfs/sys"
    assert env["HOST_ETC"] == "/hostfs/etc"
    host_mount = next(
        mount for mount in node_container["volumeMounts"] if mount["name"] == "host-root"
    )
    assert host_mount["mountPath"] == "/hostfs"
    assert host_mount["readOnly"] is True


def test_collector_workloads_are_active_resource_bounded_and_hardened():
    documents = _load_documents()
    workloads = [
        _find_document(documents, "Deployment", "k3s-vmagent"),
        _find_document(documents, "Deployment", "k3s-kube-state-metrics"),
        _find_document(documents, "Deployment", "k3s-metric-telegraf"),
        _find_document(documents, "DaemonSet", "k3s-node-telegraf"),
    ]

    for workload in workloads:
        if workload["kind"] == "Deployment":
            assert workload["spec"]["replicas"] == 1
        container = workload["spec"]["template"]["spec"]["containers"][0]
        assert container["imagePullPolicy"] == "IfNotPresent"
        assert set(container["resources"]) == {"requests", "limits"}
        assert container["resources"]["requests"]["cpu"]
        assert container["resources"]["requests"]["memory"]
        assert container["resources"]["limits"]["cpu"]
        assert container["resources"]["limits"]["memory"]
        security_context = container["securityContext"]
        assert security_context["allowPrivilegeEscalation"] is False
        assert security_context["capabilities"]["drop"] == ["ALL"]
        assert security_context["readOnlyRootFilesystem"] is True
        assert security_context["runAsNonRoot"] is True
        assert security_context["seccompProfile"] == {"type": "RuntimeDefault"}


def test_vmagent_writes_remote_queue_only_to_the_bounded_tmp_volume():
    documents = _load_documents()
    deployment = _find_document(documents, "Deployment", "k3s-vmagent")
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]

    assert "--remoteWrite.tmpDataPath=/tmp/vmagent-remotewrite-data" in container["args"]
    assert {
        "name": "tmp",
        "mountPath": "/tmp",
    } in container["volumeMounts"]
    assert {
        "name": "tmp",
        "emptyDir": {"sizeLimit": "256Mi"},
    } in pod_spec["volumes"]
