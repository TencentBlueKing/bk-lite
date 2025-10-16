"""Kubernetes集群检查和连接工具"""
import json
import subprocess
from kubernetes.client import ApiException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from kubernetes import client
from neco.llm.tools.kubernetes.utils import prepare_context


@tool()
def verify_kubernetes_connection(config: RunnableConfig = None):
    """
    验证与Kubernetes集群的连接状态

    执行基本的连接测试，类似于 kubectl cluster-info

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        str: JSON格式的连接状态信息
    """
    try:
        prepare_context(config)

        # 测试API服务器连接
        core_v1 = client.CoreV1Api()
        version_info = core_v1.api_client.call_api('/version', 'GET')

        # 获取集群信息
        cluster_info = {
            "connection_status": "成功",
            "kubernetes_version": version_info[0].get('gitVersion', 'Unknown'),
            "api_server": "可访问",
            "platform": version_info[0].get('platform', 'Unknown')
        }

        # 测试基本权限
        try:
            namespaces = core_v1.list_namespace(limit=1)
            cluster_info["permissions"] = "有基本读取权限"
            cluster_info["namespace_access"] = "正常"
        except ApiException as e:
            cluster_info["permissions"] = f"权限受限: {e.reason}"
            cluster_info["namespace_access"] = "受限"

        return json.dumps(cluster_info)

    except Exception as e:
        return json.dumps({
            "connection_status": "失败",
            "error": str(e),
            "suggestion": "请检查kubeconfig配置和网络连接"
        })


@tool()
def get_kubernetes_contexts(config: RunnableConfig = None):
    """
    获取kubectl上下文信息

    显示当前可用的上下文和当前活动的上下文

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        str: JSON格式的上下文信息
    """
    try:
        from kubernetes import config as k8s_config

        contexts, active_context = k8s_config.list_kube_config_contexts()

        result = {
            "current_context": active_context['name'] if active_context else None,
            "available_contexts": []
        }

        for context in contexts:
            context_info = {
                "name": context['name'],
                "cluster": context['context'].get('cluster'),
                "user": context['context'].get('user'),
                "namespace": context['context'].get('namespace', 'default'),
                "is_current": context['name'] == (active_context['name'] if active_context else None)
            }
            result["available_contexts"].append(context_info)

        return json.dumps(result)

    except Exception as e:
        return json.dumps({
            "error": f"获取上下文失败: {str(e)}",
            "suggestion": "请检查kubeconfig文件是否存在且格式正确"
        })


@tool()
def list_kubernetes_api_resources(api_group=None, config: RunnableConfig = None):
    """
    列出Kubernetes API资源

    显示集群中可用的API资源类型，类似于 kubectl api-resources

    Args:
        api_group (str, optional): 特定的API组，如果为None则显示所有
        config (RunnableConfig): 工具配置

    Returns:
        str: JSON格式的API资源列表
    """
    try:
        prepare_context(config)

        # 获取API组和版本
        client_instance = client.ApiClient()
        api_client = client.ApisApi(client_instance)
        core_api = client.CoreV1Api(client_instance)

        resources = []

        # 获取核心API资源 (v1)
        try:
            core_resources = core_api.get_api_resources()
            for resource in core_resources.resources:
                if '/' not in resource.name:  # 排除子资源
                    resources.append({
                        "name": resource.name,
                        "short_names": resource.short_names or [],
                        "api_version": "v1",
                        "kind": resource.kind,
                        "namespaced": resource.namespaced,
                        "verbs": resource.verbs or []
                    })
        except Exception as e:
            pass  # 忽略核心API访问错误

        # 获取其他API组的资源
        try:
            api_groups = api_client.get_api_versions()
            for group in api_groups.groups:
                if api_group and group.name != api_group:
                    continue

                for version in group.versions:
                    try:
                        # 构造API路径
                        api_path = f"/apis/{group.name}/{version.version}"
                        api_resources = client_instance.call_api(
                            api_path, 'GET', response_type='object'
                        )[0]

                        if 'resources' in api_resources:
                            for resource in api_resources['resources']:
                                if '/' not in resource['name']:  # 排除子资源
                                    resources.append({
                                        "name": resource['name'],
                                        "short_names": resource.get('shortNames', []),
                                        "api_version": f"{group.name}/{version.version}",
                                        "kind": resource['kind'],
                                        "namespaced": resource['namespaced'],
                                        "verbs": resource.get('verbs', [])
                                    })
                    except Exception as e:
                        continue  # 忽略特定版本的错误

        except Exception as e:
            pass  # 忽略API组访问错误

        # 按名称排序
        resources.sort(key=lambda x: x['name'])

        return json.dumps({
            "api_resources": resources,
            "total_count": len(resources),
            "filtered_by": api_group if api_group else "所有API组"
        })

    except Exception as e:
        return json.dumps({
            "error": f"获取API资源失败: {str(e)}",
            "api_resources": [],
            "total_count": 0
        })


@tool()
def explain_kubernetes_resource(resource_type, config: RunnableConfig = None):
    """
    解释Kubernetes资源类型

    提供指定资源类型的详细说明，类似于 kubectl explain

    Args:
        resource_type (str): 资源类型，如 'pod', 'deployment', 'service'
        config (RunnableConfig): 工具配置

    Returns:
        str: 资源类型的详细说明
    """
    # 预定义的资源说明
    resource_explanations = {
        "pod": {
            "description": "Pod是Kubernetes中最小的可部署计算单元",
            "purpose": "Pod代表集群中运行的进程",
            "key_fields": {
                "spec.containers": "Pod中的容器列表",
                "spec.restartPolicy": "重启策略 (Always, OnFailure, Never)",
                "spec.nodeSelector": "节点选择器",
                "status.phase": "Pod的生命周期阶段"
            },
            "common_uses": [
                "运行应用程序容器",
                "临时任务执行",
                "数据库实例"
            ]
        },
        "deployment": {
            "description": "Deployment为Pod和ReplicaSet提供声明式更新",
            "purpose": "管理应用程序的部署和扩缩容",
            "key_fields": {
                "spec.replicas": "期望的Pod副本数",
                "spec.selector": "标签选择器",
                "spec.template": "Pod模板",
                "spec.strategy": "部署策略"
            },
            "common_uses": [
                "无状态应用部署",
                "滚动更新",
                "扩缩容管理"
            ]
        },
        "service": {
            "description": "Service是访问Pod的抽象方式",
            "purpose": "为Pod提供稳定的网络端点",
            "key_fields": {
                "spec.selector": "选择目标Pod的标签",
                "spec.ports": "服务端口配置",
                "spec.type": "服务类型 (ClusterIP, NodePort, LoadBalancer)",
                "spec.clusterIP": "集群内部IP"
            },
            "common_uses": [
                "负载均衡",
                "服务发现",
                "外部访问入口"
            ]
        },
        "configmap": {
            "description": "ConfigMap用于存储非敏感的配置数据",
            "purpose": "将配置与容器镜像分离",
            "key_fields": {
                "data": "配置数据键值对",
                "binaryData": "二进制配置数据"
            },
            "common_uses": [
                "应用程序配置",
                "环境变量",
                "配置文件"
            ]
        },
        "secret": {
            "description": "Secret用于存储敏感数据",
            "purpose": "安全地传递敏感信息给Pod",
            "key_fields": {
                "data": "Base64编码的敏感数据",
                "type": "Secret类型 (Opaque, kubernetes.io/tls等)"
            },
            "common_uses": [
                "数据库密码",
                "API密钥",
                "TLS证书"
            ]
        },
        "namespace": {
            "description": "Namespace提供资源的逻辑隔离",
            "purpose": "在同一集群中创建多个虚拟集群",
            "key_fields": {
                "status.phase": "命名空间状态"
            },
            "common_uses": [
                "环境隔离 (dev, staging, prod)",
                "团队隔离",
                "资源配额管理"
            ]
        },
        "node": {
            "description": "Node是Kubernetes集群中的工作节点",
            "purpose": "提供计算资源运行Pod",
            "key_fields": {
                "status.conditions": "节点健康状态",
                "status.capacity": "节点总容量",
                "status.allocatable": "可分配资源",
                "spec.taints": "节点污点"
            },
            "common_uses": [
                "工作负载调度目标",
                "资源管理",
                "集群扩缩容"
            ]
        }
    }

    resource_type = resource_type.lower()

    if resource_type in resource_explanations:
        explanation = resource_explanations[resource_type]

        result = {
            "resource_type": resource_type,
            "description": explanation["description"],
            "purpose": explanation["purpose"],
            "key_fields": explanation["key_fields"],
            "common_uses": explanation["common_uses"],
            "api_version": _get_api_version_for_resource(resource_type)
        }

        return json.dumps(result, ensure_ascii=False, indent=2)
    else:
        return json.dumps({
            "resource_type": resource_type,
            "error": f"暂不支持资源类型 '{resource_type}' 的说明",
            "supported_types": list(resource_explanations.keys()),
            "suggestion": "请使用 list_kubernetes_api_resources 查看所有可用的资源类型"
        }, ensure_ascii=False)


@tool()
def describe_kubernetes_resource(resource_type, resource_name, namespace=None, config: RunnableConfig = None):
    """
    描述指定的Kubernetes资源

    获取资源的详细信息，类似于 kubectl describe

    Args:
        resource_type (str): 资源类型 (pod, deployment, service等)
        resource_name (str): 资源名称
        namespace (str, optional): 命名空间，某些资源类型需要
        config (RunnableConfig): 工具配置

    Returns:
        str: JSON格式的资源详细描述
    """
    try:
        prepare_context(config)

        core_v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()

        resource_type = resource_type.lower()

        if resource_type == "pod":
            if not namespace:
                return json.dumps({"error": "Pod资源需要指定namespace"})
            resource = core_v1.read_namespaced_pod(resource_name, namespace)
        elif resource_type == "deployment":
            if not namespace:
                return json.dumps({"error": "Deployment资源需要指定namespace"})
            resource = apps_v1.read_namespaced_deployment(
                resource_name, namespace)
        elif resource_type == "service":
            if not namespace:
                return json.dumps({"error": "Service资源需要指定namespace"})
            resource = core_v1.read_namespaced_service(
                resource_name, namespace)
        elif resource_type == "node":
            resource = core_v1.read_node(resource_name)
        elif resource_type == "namespace":
            resource = core_v1.read_namespace(resource_name)
        else:
            return json.dumps({
                "error": f"暂不支持资源类型: {resource_type}",
                "supported_types": ["pod", "deployment", "service", "node", "namespace"]
            })

        # 转换为字典格式
        resource_dict = client.ApiClient().sanitize_for_serialization(resource)

        # 提取关键信息
        description = {
            "name": resource_dict.get("metadata", {}).get("name"),
            "namespace": resource_dict.get("metadata", {}).get("namespace"),
            "resource_type": resource_type,
            "creation_timestamp": resource_dict.get("metadata", {}).get("creationTimestamp"),
            "labels": resource_dict.get("metadata", {}).get("labels", {}),
            "annotations": resource_dict.get("metadata", {}).get("annotations", {}),
            "spec": resource_dict.get("spec", {}),
            "status": resource_dict.get("status", {})
        }

        return json.dumps(description, default=str, ensure_ascii=False, indent=2)

    except ApiException as e:
        if e.status == 404:
            return json.dumps({
                "error": f"资源不存在: {resource_type}/{resource_name}",
                "namespace": namespace,
                "status_code": 404
            })
        else:
            return json.dumps({
                "error": f"获取资源失败: {str(e)}",
                "status_code": e.status if hasattr(e, 'status') else 'unknown'
            })
    except Exception as e:
        return json.dumps({"error": f"描述资源时发生错误: {str(e)}"})


def _get_api_version_for_resource(resource_type):
    """获取资源类型对应的API版本"""
    api_versions = {
        "pod": "v1",
        "service": "v1",
        "namespace": "v1",
        "node": "v1",
        "configmap": "v1",
        "secret": "v1",
        "deployment": "apps/v1",
        "replicaset": "apps/v1",
        "daemonset": "apps/v1",
        "statefulset": "apps/v1"
    }
    return api_versions.get(resource_type, "未知")


@tool()
def kubernetes_troubleshooting_guide(keyword, namespace=None, config: RunnableConfig = None):
    """
    Kubernetes故障排查指导

    基于关键词提供系统化的故障排查指导流程

    Args:
        keyword (str): 故障关键词，如 'pod', 'network', 'storage', 'performance'
        namespace (str, optional): 相关的命名空间
        config (RunnableConfig): 工具配置

    Returns:
        str: JSON格式的故障排查指导
    """
    keyword = keyword.lower()

    troubleshooting_guides = {
        "pod": {
            "title": "Pod故障排查指导",
            "steps": [
                {
                    "step": 1,
                    "action": "检查Pod状态",
                    "command": "kubectl get pods -n <namespace>",
                    "check": "查看Pod的STATUS列，常见状态：Running, Pending, CrashLoopBackOff, Error"
                },
                {
                    "step": 2,
                    "action": "查看Pod详细信息",
                    "command": "kubectl describe pod <pod-name> -n <namespace>",
                    "check": "检查Events部分的错误信息和Warning"
                },
                {
                    "step": 3,
                    "action": "检查Pod日志",
                    "command": "kubectl logs <pod-name> -n <namespace>",
                    "check": "查看应用程序日志中的错误信息"
                },
                {
                    "step": 4,
                    "action": "检查资源限制",
                    "command": "kubectl top pod <pod-name> -n <namespace>",
                    "check": "检查CPU和内存使用情况是否超出限制"
                },
                {
                    "step": 5,
                    "action": "检查节点状态",
                    "command": "kubectl get nodes",
                    "check": "确认Pod所在节点是否健康"
                }
            ],
            "common_issues": [
                "ImagePullBackOff: 镜像拉取失败",
                "CrashLoopBackOff: 容器启动后立即崩溃",
                "Pending: Pod无法被调度到节点",
                "OOMKilled: 内存超出限制被杀死"
            ]
        },
        "network": {
            "title": "网络故障排查指导",
            "steps": [
                {
                    "step": 1,
                    "action": "检查Service状态",
                    "command": "kubectl get svc -n <namespace>",
                    "check": "确认Service是否存在且配置正确"
                },
                {
                    "step": 2,
                    "action": "检查Endpoints",
                    "command": "kubectl get endpoints -n <namespace>",
                    "check": "确认Service后端Pod是否正常注册"
                },
                {
                    "step": 3,
                    "action": "测试Pod间连通性",
                    "command": "kubectl exec -it <pod> -- ping <target-ip>",
                    "check": "测试Pod之间的网络连通性"
                },
                {
                    "step": 4,
                    "action": "检查NetworkPolicy",
                    "command": "kubectl get networkpolicy -n <namespace>",
                    "check": "确认网络策略是否阻止了连接"
                },
                {
                    "step": 5,
                    "action": "检查DNS解析",
                    "command": "kubectl exec -it <pod> -- nslookup <service-name>",
                    "check": "测试Service的DNS解析是否正常"
                }
            ],
            "common_issues": [
                "Service无法访问: 检查选择器和端口配置",
                "DNS解析失败: 检查CoreDNS状态",
                "NetworkPolicy阻止: 检查网络策略配置",
                "Pod间通信失败: 检查CNI网络插件"
            ]
        },
        "storage": {
            "title": "存储故障排查指导",
            "steps": [
                {
                    "step": 1,
                    "action": "检查PVC状态",
                    "command": "kubectl get pvc -n <namespace>",
                    "check": "确认PVC状态是否为Bound"
                },
                {
                    "step": 2,
                    "action": "检查PV状态",
                    "command": "kubectl get pv",
                    "check": "确认PV是否可用且未被其他PVC占用"
                },
                {
                    "step": 3,
                    "action": "检查StorageClass",
                    "command": "kubectl get storageclass",
                    "check": "确认存储类是否存在且配置正确"
                },
                {
                    "step": 4,
                    "action": "检查Pod挂载状态",
                    "command": "kubectl describe pod <pod-name> -n <namespace>",
                    "check": "查看Volume挂载相关的事件和错误"
                },
                {
                    "step": 5,
                    "action": "检查存储后端",
                    "command": "检查存储提供商的状态",
                    "check": "确认底层存储系统是否正常"
                }
            ],
            "common_issues": [
                "PVC Pending: 没有匹配的PV或StorageClass",
                "挂载失败: 节点权限或存储后端问题",
                "数据丢失: 检查PV的回收策略",
                "性能问题: 检查存储IOPS和带宽限制"
            ]
        },
        "performance": {
            "title": "性能问题排查指导",
            "steps": [
                {
                    "step": 1,
                    "action": "检查资源使用情况",
                    "command": "kubectl top nodes && kubectl top pods --all-namespaces",
                    "check": "识别CPU和内存使用率高的节点和Pod"
                },
                {
                    "step": 2,
                    "action": "检查资源限制配置",
                    "command": "kubectl describe pod <pod-name> -n <namespace>",
                    "check": "确认Requests和Limits是否合理设置"
                },
                {
                    "step": 3,
                    "action": "检查HPA状态",
                    "command": "kubectl get hpa -n <namespace>",
                    "check": "确认自动扩缩容是否正常工作"
                },
                {
                    "step": 4,
                    "action": "分析应用程序日志",
                    "command": "kubectl logs <pod-name> -n <namespace>",
                    "check": "查找性能瓶颈和错误日志"
                },
                {
                    "step": 5,
                    "action": "检查节点负载",
                    "command": "kubectl describe node <node-name>",
                    "check": "确认节点资源分配和压力情况"
                }
            ],
            "common_issues": [
                "CPU瓶颈: 增加CPU限制或优化应用程序",
                "内存不足: 增加内存限制或优化内存使用",
                "I/O瓶颈: 检查存储性能和网络带宽",
                "调度延迟: 检查资源碎片化和亲和性规则"
            ]
        }
    }

    if keyword in troubleshooting_guides:
        guide = troubleshooting_guides[keyword]
        guide["namespace_context"] = namespace
        guide["timestamp"] = "故障排查指导生成时间"

        return json.dumps(guide, ensure_ascii=False, indent=2)
    else:
        return json.dumps({
            "error": f"暂不支持关键词: {keyword}",
            "available_keywords": list(troubleshooting_guides.keys()),
            "suggestion": "请选择一个支持的故障排查类别"
        }, ensure_ascii=False)
