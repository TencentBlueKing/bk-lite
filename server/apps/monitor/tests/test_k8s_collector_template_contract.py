# -- coding: utf-8 --
"""K8s 采集器模板契约测试。

监控链路的 K8s 对象实例发现（Pod/Node 等衍生对象）与 K8s 仪表盘依赖
vmagent 抓取 kube-state-metrics 后 remote write 出的
`prometheus_remote_write_kube_*` 指标；CMDB 链路则由 telegraf-resource
直抓 KSM 上报 `prometheus_kube_*`。两条链路共享同一个 KSM 实例
（三份模板都自带同名同 args 的 KSM，任意组合部署都完整），采集侧各自精确过滤。

本测试锁定三份模板之间的消费契约，防止再次出现"webhookd 下发版
vmagent 缺 KSM 抓取 job，导致监控 K8s 对象全部无实例"的静默断供
（2026-07-16 生产案例，openspec resource-collector-template 拆分遗留）。
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
WEBHOOKD_METRIC = REPO_ROOT / "agents/webhookd/bk-lite-metric-collector.yaml"
WEBHOOKD_RESOURCE = REPO_ROOT / "agents/webhookd/bk-lite-resource-collector.yaml"
DIST_METRIC = REPO_ROOT / "deploy/dist/bk-lite-kubernetes-collector/bk-lite-metric-collector.yaml"
METRICS_JSON = REPO_ROOT / "server/apps/monitor/support-files/plugins/unknown/k8s/k8s/metrics.json"
WEB_K8S_DASHBOARDS = REPO_ROOT / "web/src/app/monitor/dashboards/objects"

KSM_JOB_NAME = "kubernetes-kube-state-metrics"
CADVISOR_JOB_NAME = "kubernetes-cadvisor"
REMOTE_WRITE_PREFIX = "prometheus_remote_write_"
# 三份都自带 KSM（同名共享实例）：metric-only / resource-only / 双装任意组合都功能完整
KSM_TEMPLATES = (DIST_METRIC, WEBHOOKD_METRIC, WEBHOOKD_RESOURCE)


def load_docs(path):
    return [doc for doc in yaml.safe_load_all(path.read_text()) if doc]


def find_docs(docs, kind, name=None):
    return [doc for doc in docs if doc.get("kind") == kind and (name is None or doc.get("metadata", {}).get("name") == name)]


def vmagent_scrape_jobs(path):
    """解析模板中 vmagent-config 的 prometheus.yml，返回 {job_name: job}。"""
    docs = load_docs(path)
    configmaps = find_docs(docs, "ConfigMap", "vmagent-config")
    assert configmaps, f"{path} 中未找到 ConfigMap vmagent-config"
    prom = yaml.safe_load(configmaps[0]["data"]["prometheus.yml"])
    return {job["job_name"]: job for job in prom["scrape_configs"]}


def keep_metric_names(job):
    """提取 job 的 metric_relabel_configs 中按 __name__ keep 的指标名集合。"""
    for relabel in job.get("metric_relabel_configs", []):
        if relabel.get("action") == "keep" and relabel.get("source_labels") == ["__name__"]:
            return set(relabel["regex"].split("|"))
    raise AssertionError(f"job {job.get('job_name')} 缺少按 __name__ keep 的 metric_relabel 规则")


def labeldrop_regexes(job):
    return {relabel["regex"] for relabel in job.get("metric_relabel_configs", []) if relabel.get("action") == "labeldrop"}


def consumed_ksm_metrics():
    """从监控插件定义与 web K8s 仪表盘中提取消费的 KSM 指标名（去 remote write 前缀）。"""
    texts = [METRICS_JSON.read_text()]
    for dashboard_dir in WEB_K8S_DASHBOARDS.glob("k8s-*"):
        for file in dashboard_dir.rglob("*"):
            if file.is_file():
                texts.append(file.read_text(errors="ignore"))
    consumed = set()
    for text in texts:
        for token in re.findall(rf"{REMOTE_WRITE_PREFIX}(kube_\w+)", text):
            consumed.add(token)
    assert consumed, "未在 metrics.json 与 web 仪表盘中提取到任何 KSM 指标，契约测试的扫描路径可能失效"
    return consumed


def test_webhookd_vmagent_scrapes_kube_state_metrics():
    """webhookd 下发版 vmagent 必须包含 KSM 抓取 job，否则监控 K8s 对象实例发现断供。"""
    jobs = vmagent_scrape_jobs(WEBHOOKD_METRIC)
    assert KSM_JOB_NAME in jobs, (
        f"webhookd 版 vmagent-config 缺少 '{KSM_JOB_NAME}' 抓取 job：监控链路将没有 "
        f"{REMOTE_WRITE_PREFIX}kube_* 指标，Pod/Node 等监控实例无法被发现"
    )


def test_vmagent_ksm_keep_covers_monitor_consumption():
    """监控侧消费的 KSM 指标集合必须 ⊆ vmagent KSM job 的 keep 白名单。"""
    consumed = consumed_ksm_metrics()
    for template in (WEBHOOKD_METRIC, DIST_METRIC):
        jobs = vmagent_scrape_jobs(template)
        assert KSM_JOB_NAME in jobs, f"{template} 缺少 {KSM_JOB_NAME} job"
        kept = keep_metric_names(jobs[KSM_JOB_NAME])
        missing = consumed - kept
        assert not missing, f"{template} 的 KSM keep 白名单缺少监控侧消费的指标: {sorted(missing)}"


def test_vmagent_ksm_job_consistent_between_templates():
    """webhookd 版与 deploy/dist 手动版的 KSM job 过滤规则必须一致，防止双模板漂移。"""
    webhookd_jobs = vmagent_scrape_jobs(WEBHOOKD_METRIC)
    dist_jobs = vmagent_scrape_jobs(DIST_METRIC)
    assert KSM_JOB_NAME in webhookd_jobs and KSM_JOB_NAME in dist_jobs
    webhookd_job, dist_job = webhookd_jobs[KSM_JOB_NAME], dist_jobs[KSM_JOB_NAME]
    assert keep_metric_names(webhookd_job) == keep_metric_names(dist_job), "两模板 KSM keep 指标集不一致"
    assert labeldrop_regexes(webhookd_job) == labeldrop_regexes(dist_job), "两模板 KSM labeldrop 规则不一致"
    assert webhookd_job.get("relabel_configs") == dist_job.get("relabel_configs"), "两模板 KSM 服务发现 relabel 不一致"


def test_vmagent_cadvisor_job_consistent_between_templates():
    """cadvisor job 的过滤规则两模板同步（PR #3933 约束）。"""
    webhookd_job = vmagent_scrape_jobs(WEBHOOKD_METRIC)[CADVISOR_JOB_NAME]
    dist_job = vmagent_scrape_jobs(DIST_METRIC)[CADVISOR_JOB_NAME]
    assert keep_metric_names(webhookd_job) == keep_metric_names(dist_job), "两模板 cadvisor keep 指标集不一致"
    assert labeldrop_regexes(webhookd_job) == labeldrop_regexes(dist_job), "两模板 cadvisor labeldrop 规则不一致"


def ksm_deployment(path):
    deployments = find_docs(load_docs(path), "Deployment", "kube-state-metrics")
    assert deployments, f"{path} 中未找到 kube-state-metrics Deployment"
    return deployments[0]


def test_vmagent_ksm_discovery_matches_ksm_pod_metadata():
    """vmagent KSM job 的服务发现条件必须与各模板部署的 KSM pod 元数据匹配。

    KSM 是同名共享实例（三份模板都自带），vmagent 按 pod label + annotation
    发现——发现条件与 pod labels/annotations 对不上时会静默断供。
    """
    jobs = vmagent_scrape_jobs(WEBHOOKD_METRIC)
    job = jobs[KSM_JOB_NAME]

    keep_conditions = {
        tuple(relabel["source_labels"]): relabel["regex"] for relabel in job.get("relabel_configs", []) if relabel.get("action") == "keep"
    }
    expected_label_condition = ("__meta_kubernetes_pod_label_app_kubernetes_io_name",)
    expected_scrape_condition = ("__meta_kubernetes_pod_annotation_prometheus_io_scrape",)
    assert keep_conditions.get(expected_label_condition) == "kube-state-metrics"
    assert str(keep_conditions.get(expected_scrape_condition)).lower() == "true"

    for template in KSM_TEMPLATES:
        pod_meta = ksm_deployment(template)["spec"]["template"]["metadata"]
        assert pod_meta["labels"].get("app.kubernetes.io/name") == "kube-state-metrics", f"{template} KSM pod 缺少发现 label"
        assert str(pod_meta["annotations"].get("prometheus.io/scrape")).lower() == "true", f"{template} KSM pod 缺少 scrape annotation"
        assert pod_meta["annotations"].get("prometheus.io/port") == "8080", f"{template} KSM pod 缺少 port annotation"


def test_ksm_stack_present_in_all_ksm_templates():
    """三份模板都必须自带完整 KSM 资源栈：metric-only / resource-only / 双装任意组合都功能完整。"""
    for template in KSM_TEMPLATES:
        docs = load_docs(template)
        for kind in ("Deployment", "Service", "ServiceAccount", "ClusterRole", "ClusterRoleBinding"):
            assert find_docs(docs, kind, "kube-state-metrics"), f"{template} 缺少 kube-state-metrics {kind}"


def test_ksm_args_identical_across_templates():
    """KSM 是同名共享实例：三份含 KSM 的模板 args 必须逐字一致（两链路消费指标的并集），
    否则同集群任意组合共装时后 apply 者覆盖先 apply 者，必有一条链路静默断供。"""

    def ksm_args(path):
        containers = ksm_deployment(path)["spec"]["template"]["spec"]["containers"]
        return next(c["args"] for c in containers if c["name"] == "kube-state-metrics")

    baseline_template, baseline_args = KSM_TEMPLATES[0], ksm_args(KSM_TEMPLATES[0])
    baseline_pod_meta = ksm_deployment(baseline_template)["spec"]["template"]["metadata"]
    for template in KSM_TEMPLATES[1:]:
        assert ksm_args(template) == baseline_args, f"{template} 的 KSM args 与 {baseline_template} 不一致，同集群共装时会互相覆盖断供"
        assert (
            ksm_deployment(template)["spec"]["template"]["metadata"] == baseline_pod_meta
        ), f"{template} 的 KSM pod labels/annotations 与 {baseline_template} 不一致，vmagent 服务发现条件可能失配"
