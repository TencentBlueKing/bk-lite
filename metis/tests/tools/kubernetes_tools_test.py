import os

from loguru import logger

from src.tools.kubernetes_tools import get_kubernetes_namespaces, list_kubernetes_pods, list_kubernetes_nodes, \
    list_kubernetes_deployments, list_kubernetes_services, list_kubernetes_events, get_failed_kubernetes_pods, \
    get_pending_kubernetes_pods, get_high_restart_kubernetes_pods, get_kubernetes_node_capacity, \
    get_kubernetes_orphaned_resources, get_kubernetes_resource_yaml, get_kubernetes_pod_logs, get_kubernetes_pod_logs


def test_get_kubernetes_namespaces():
    rs = get_kubernetes_namespaces.run('', config={
        'configurable': {
            'kubeconfig_path': os.environ['TEST_KUBECONFIG_PATH'],
        }
    })
    logger.info(rs)


def test_list_kubernetes_pods():
    rs = list_kubernetes_pods.run('kube-system', config={
        'configurable': {
            'kubeconfig_path': os.environ['TEST_KUBECONFIG_PATH'],
        }
    })
    logger.info(rs)


def test_list_kubernetes_nodes():
    rs = list_kubernetes_nodes.run('', config={
        'configurable': {
            'kubeconfig_path': os.environ['TEST_KUBECONFIG_PATH'],
        }
    })
    logger.info(rs)


def test_list_kubernetes_deployments():
    rs = list_kubernetes_deployments.run('kube-system', config={
        'configurable': {
            'kubeconfig_path': os.environ['TEST_KUBECONFIG_PATH'],
        }
    })
    logger.info(rs)


def test_list_kubernetes_services():
    rs = list_kubernetes_services.run('kube-system', config={
        'configurable': {
            'kubeconfig_path': os.environ['TEST_KUBECONFIG_PATH'],
        }
    })
    logger.info(rs)


def test_list_kubernetes_events():
    rs = list_kubernetes_events.run('kube-system', config={
        'configurable': {
            'kubeconfig_path': os.environ['TEST_KUBECONFIG_PATH'],
        }
    })
    logger.info(rs)


def test_get_failed_kubernetes_pods():
    rs = get_failed_kubernetes_pods.run('', config={
        'configurable': {
            'kubeconfig_path': os.environ['TEST_KUBECONFIG_PATH'],
        }
    })
    logger.info(rs)


def test_get_pending_kubernetes_pods():
    rs = get_pending_kubernetes_pods.run('', config={
        'configurable': {
            'kubeconfig_path': os.environ['TEST_KUBECONFIG_PATH'],
        }
    })
    logger.info(rs)


def test_get_high_restart_kubernetes_pods():
    rs = get_high_restart_kubernetes_pods.run({
        'restart_threshold': 1
    }, config={
        'configurable': {
            'kubeconfig_path': os.environ['TEST_KUBECONFIG_PATH'],
        }
    })
    logger.info(rs)


def test_get_kubernetes_node_capacity():
    rs = get_kubernetes_node_capacity.run('', config={
        'configurable': {
            'kubeconfig_path': os.environ['TEST_KUBECONFIG_PATH'],
        }
    })
    logger.info(rs)


def test_get_kubernetes_orphaned_resources():
    rs = get_kubernetes_orphaned_resources.run('', config={
        'configurable': {
            'kubeconfig_path': os.environ['TEST_KUBECONFIG_PATH'],
        }
    })
    logger.info(rs)


def test_get_kubernetes_resource_yaml():
    rs = get_kubernetes_resource_yaml.run({
        'namespace': 'kube-system',
        'resource_type': 'pod',
        'resource_name': 'kube-apiserver-minikube'
    }, config={
        'configurable': {
            'kubeconfig_path': os.environ['TEST_KUBECONFIG_PATH'],
        }
    })
    logger.info(rs)


def test_get_kubernetes_pod_logs():
    rs = get_kubernetes_pod_logs.run({
        'namespace': 'kube-system',
        'pod_name': 'coredns-7b98449c4-8zc9w',
        'container': None,
        'lines': 50,
        'tail': True
    }, config={
        'configurable': {
            'kubeconfig_path': os.environ['TEST_KUBECONFIG_PATH'],
        }
    })
    logger.info(rs)
