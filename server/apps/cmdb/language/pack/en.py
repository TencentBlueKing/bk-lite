CLASSIFICATION = {
    "biz_manage": "Biz",
    "host_manage": "Host",
    "database": "Database",
    "middleware": "Middleware",
    "docker": "Docker",
    "device": "Device",
    "K8S": "K8S",
    "vmware": "VMware",
    "alibaba_cloud": "Alibaba Cloud",
    "tencent_cloud": "Tencent Cloud",
    "huaweicloud": "Huawei Cloud",
    "azure": "Azure",
    "certificate": "Certificate",
    "domain": "Domain",
}

MODEL = {
    "biz": "Biz",
    "module": "Module",
    "host": "Host",
    "oracle": "Oracle",
    "mysql": "MySQL",
    "mssql": "MSSQL",
    "redis": "Redis",
    "mongodb": "MongoDB",
    "elasticsearch": "ElasticSearch",
    "postgresql": "PostgreSQL",
    "db2": "DB2",
    "db_cluster": "DB Cluster",
    "apache": "Apache",
    "tomcat": "Tomcat",
    "nginx": "Nginx",
    "iis": "IIS",
    "rabbitmq": "RabbitMQ",
    "weblogic": "WebLogic",
    "websphere": "websphere",
    "kafka": "Kafka",
    "ibmmq": "IBM MQ",
    "zookeeper": "ZooKeeper",
    "nacos": "Nacos",
    "minio": "Minio",
    "docker": "Docker",
    "docker_container": "Docker Container",
    "docker_image": "Docker Image",
    "docker_network": "Docker Network",
    "docker_volume": "Docker Volume",
    "switch": "Switch",
    "router": "Router",
    "loadbalance": "Loadbalance",
    "firewall": "Firewall",
    "hard_server": "Hard Server",
    "storage": "Storage",
    "security_equipment": "Security Equipment",
    "interface": "Interface",
    "k8s_cluster": "K8S Cluster",
    "k8s_namespace": "K8S Namespace",
    "k8s_workload": "K8S Workload",
    "k8s_node": "K8S Node",
    "k8s_pod": "K8S Pod",
    "vmware_vc": "vCenter",
    "vmware_vm": "VMware VM",
    "vmware_esxi": "ESXi",
    "vmware_ds": "Data Storage",
    "alibabacloud_platform": "Alibaba Cloud",
    "alibabacloud_ecs": "Alibabacloud ECS",
    "tencentcloud_platform": "Tencent Cloud",
    "tencentcloud_cvm": "Tencentcloud CVM",
    "huaweicloud_platform": "Huawei Cloud",
    "huaweicloud_ecs": "Huaweicloud ECS",
    "azure_platform": "Azure",
    "azure_vm": "Azure VM",
    "ssl_certificate": "SSL Certificate",
    "domain": "Domain",
}

ATTR = {
    "biz": {
        "inst_name": "Name",
        "organization": "Organization",
        "status": "Status",
        "maintainer": "Maintainer",
        "developer": "Developer",
        "productor": "Productor",
        "tester": "Tester",
        "description": "Description",
    },
    "module": {
        "inst_name": "Name",
        "organization": "Organization",
        "module_type": "Type",
        "operator": "Operator",
        "bak_operator": "Bak Operator",
    },
    "host": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "host_outerip": "Outerip",
        "os_type": "Type",
        "os_version": "Version",
        "os_bit": "Bit",
        "cpu": "CPU",
        "cpu_module": "CPU Module",
        "cpu_architecture": "CPU Architecture",
        "memory": "Memory",
        "disk": "Disk",
        "mac": "MAC",
        "outer_mac": "Outer MAC",
        "operator": "Operator",
        "comment": "Comment",
    },
    "oracle": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "port": "Port",
        "sid": "SID",
        "max_mem": "MAX Memory",
        "max_conn": "MAX Connect",
        "version": "Version",
        "database_role": "Database Role",
    },
    "mysql": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "port": "Port",
        "version": "Version",
        "enable_binlog": "Binlog",
        "max_conn": "MAX Memory",
        "max_mem": "MAX Connect",
        "database_role": "Database Role",
    },
    "mssql": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "port": "Port",
        "version": "Version",
        "max_connect": "MAX Connect",
        "max_memory": "MAX Memory",
        "order_rule": "Order Rule",
        "ha_mode": "HA Mode",
    },
    "redis": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "port": "Port",
        "version": "Version",
        "max_connect": "MAX Memory",
        "max_memory": "MAX Connect",
        "database_role": "Database Role",
    },
    "mongodb": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "port": "Port",
        "version": "Version",
        "database_role": "Database Role",
    },
    "elasticsearch": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "port": "Port",
        "version": "Version",
        "database_role": "Database Role",
    },
    "postgresql": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "port": "Port",
        "version": "Version",
    },
    "db2": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "port": "Port",
        "version": "Version",
        "database_role": "Database Role",
    },
    "db_cluster": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "port": "Port",
        "type": "Type",
    },
    "apache": {
        "inst_name": "Name",
        "organization": "Organization",
        "httpd_path": "Httpd Path",
        "httpd_conf_path": "Httpd Conf Path",
        "ip_addr": "IP Address",
        "port": "Port",
        "doc_root": "Doc Root",
        "version": "Version",
    },
    "tomcat": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "catalina_path": "Catalina Path",
        "version_path": "Version Path",
        "port": "Port",
        "java_version": "Java Version",
        "version": "Version",
    },
    "nginx": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "port": "Port",
        "version": "Version",
        "bin_path": "Bin Path",
        "server_name": "Server Name",
        "ssl_version": "SSL Version",
    },
    "iis": {"inst_name": "Name", "organization": "Organization", "ip_addr": "IP Address", "version": "Version"},
    "rabbitmq": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "port": "Port",
        "allport": "Allport",
        "node_name": "Node Name",
        "version": "Version",
        "erlang_version": "Erlang Version",
        "java_version": "Java Version",
    },
    "weblogic": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
    },
    "websphere": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "port": "Port",
        "admin_server_name": "Admin Server Name",
        "wlst_path": "wlst Path",
        "version": "Version",
        "domain_version": "Domain Version",
        "java_version": "Java Version",
    },
    "kafka": {"inst_name": "Name", "organization": "Organization", "ip_addr": "IP Address"},
    "ibmmq": {"inst_name": "Name", "organization": "Organization", "ip_addr": "IP Address"},
    "zookeeper": {"inst_name": "Name", "organization": "Organization", "ip_addr": "IP Address"},
    "nacos": {"inst_name": "Name", "organization": "Organization", "ip_addr": "IP Address"},
    "minio": {"inst_name": "Name", "organization": "Organization", "ip_addr": "IP Address"},
    "docker": {"inst_name": "Name", "organization": "Organization", "version": "Version", "url": "URL", "cpus": "CPU"},
    "docker_container": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "state": "State",
        "stack": "Stack",
        "port": "Port",
        "created": "Created Time",
    },
    "docker_image": {
        "inst_name": "Name",
        "organization": "Organization",
        "inst_id": "IP Address",
        "tag": "Tag",
        "size": "Size",
        "build": "Build",
        "created_time": "Created Time",
    },
    "docker_network": {
        "inst_name": "Name",
        "organization": "Organization",
        "stack": "Stack",
        "driver": "Driver",
        "attachable": "Attachable",
        "ipam_driver": "IPAM Driver",
        "ipv4_subnet": "IPV4 Subnet",
        "ipv4_gateway": "IPV4 Gateway",
        "ipv6_subnet": "IPV6 Subnet",
        "ipv6_gateway": "IPV6 Gateway",
    },
    "docker_volume": {
        "inst_name": "Name",
        "organization": "Organization",
        "stack": "Stack",
        "driver": "Driver",
        "mount_point": "Mount Point",
        "created": "Created Time",
    },
    "switch": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP address",
        "brand": "Brand",
        "model": "Model",
        "snmp_version": "Version",
        "port": "Port",
    },
    "router": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP address",
        "brand": "Brand",
        "model": "Model",
        "snmp_version": "Version",
        "port": "Port",
    },
    "loadbalance": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP address",
        "brand": "Brand",
        "model": "Model",
        "snmp_version": "Version",
        "port": "Port",
    },
    "firewall": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP address",
        "brand": "Brand",
        "model": "Model",
        "snmp_version": "Version",
        "port": "Port",
    },
    "hard_server": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP address",
        "brand": "Brand",
        "model": "Model",
        "snmp_version": "Version",
        "port": "Port",
    },
    "storage": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP address",
        "brand": "Brand",
        "model": "Model",
        "snmp_version": "Version",
        "port": "Port",
    },
    "security_equipment": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP address",
        "brand": "Brand",
        "model": "Model",
        "snmp_version": "Version",
        "port": "Port",
    },
    "interface": {
        "inst_name": "Name",
        "organization": "Organization",
        "mac": "MAC",
        "adminstatus": "Adminstatus",
        "operstatus": "Operstatus",
    },
    "k8s_cluster": {"inst_name": "Name", "organization": "Organization"},
    "k8s_namespace": {
        "inst_name": "Name",
        "name": "Namespace Name",
        "organization": "Organization",
        "collect_task": "Collection Cluster",
        "collect_time": "Collection Time",
        "auto_collect": "Auto Collect",
    },
    "k8s_workload": {
        "inst_name": "Name",
        "name": "Workload Name",
        "workload_type": "Type",
        "organization": "Organization",
        "collect_task": "Collection Cluster",
        "collect_time": "Collection Time",
        "auto_collect": "Auto Collect",
    },
    "k8s_node": {
        "inst_name": "Name",
        "name": "Node Name",
        "organization": "Organization",
        "ip_addr": "IP address",
        "role": "Role",
        "cpu": "CPU",
        "memory": "Memory",
        "storage": "Storage",
        "os_version": "OSVersion",
        "kubelet_version": "Kubelet Version",
        "kernel_version": "Kernel Version",
        "container_runtime_version": "CR Version",
        "pod_cidr": "Pod CIDR",
        "collect_task": "Collection Cluster",
        "collect_time": "Collection Time",
        "auto_collect": "Auto Collect",
    },
    "k8s_pod": {
        "inst_name": "Name",
        "name": "Pod Name",
        "organization": "Organization",
        "ip_addr": "IP address",
        "limit_cpu": "CPU Limit",
        "limit_memory": "Memory Limit",
        "request_cpu": "CPU Request",
        "request_memory": "Memory Request",
        "collect_task": "Collection Cluster",
        "collect_time": "Collection Time",
        "auto_collect": "Auto Collect",
    },
    "vmware_vc": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP address",
        "vc_version": "VC Version",
    },
    "vmware_vm": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP address",
        "resource_id": "Resource ID",
        "os_name": "OS Name",
        "vcpus": "vCPU",
        "memory": "Memory",
    },
    "vmware_esxi": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP address",
        "resource_id": "Resource ID",
        "cpu_model": "CPU Model",
        "cpu_cores": "CPU Cores",
        "vcpus": "vCPU",
        "memory": "Memory",
        "esxi_version": "Version",
    },
    "vmware_ds": {
        "inst_name": "Name",
        "organization": "Organization",
        "resource_id": "Resource ID",
        "system_type": "System Type",
        "storage": "Storage",
        "url": "URL",
    },
    "alibabacloud_platform": {"inst_name": "Name", "organization": "Organization"},
    "alibabacloud_ecs": {
        "inst_name": "Name",
        "organization": "Organization",
        "resource_id": "Resource ID",
        "ip_addr": "IP address",
        "public_ip": "Public IP",
        "region": "Region",
        "zone": "Zone",
        "vpc": "VPC",
        "status": "Status",
        "instance_type": "Type",
        "os_name": "OS Name",
        "vcpus": "vCPU",
        "memory": "Memory",
        "charge_type": "Charge Type",
        "create_time": "Create Time",
        "expired_time": "Expired Time",
    },
    "tencentcloud_platform": {"inst_name": "Name", "organization": "Organization"},
    "tencentcloud_cvm": {
        "inst_name": "Name",
        "organization": "Organization",
        "resource_id": "Resource ID",
        "ip_addr": "IP address",
        "public_ip": "Public IP",
        "region": "Region",
        "zone": "Zone",
        "vpc": "VPC",
        "status": "Status",
        "instance_type": "Type",
        "os_name": "OS Name",
        "vcpus": "vCPU",
        "memory": "Memory",
        "charge_type": "Charge Type",
        "create_time": "Create Time",
        "expired_time": "Expired Time",
    },
    "huaweicloud_platform": {"inst_name": "Name", "organization": "Organization"},
    "huaweicloud_ecs": {
        "inst_name": "Name",
        "organization": "Organization",
        "resource_id": "Resource ID",
        "ip_addr": "IP Address",
        "public_ip": "Public IP",
        "region": "Region",
        "zone": "Zone",
        "vpc": "VPC",
        "status": "Status",
        "instance_type": "Type",
        "os_name": "OS Name",
        "vcpus": "vCPU",
        "memory": "Memory",
        "charge_type": "Charge Type",
        "create_time": "Create Time",
        "expired_time": "Expired Time",
    },
    "azure_platform": {"inst_name": "Name", "organization": "Organization"},
    "azure_vm": {
        "inst_name": "Name",
        "organization": "Organization",
        "ip_addr": "IP Address",
        "region": "Region",
        "architecture": "Architecture",
        "size": "Size",
        "image": "Image",
    },
    "ssl_certificate": {
        "inst_name": "Name",
        "organization": "Organization",
        "issuer": "Issuer",
        "domain": "Domain",
        "create_time": "Create Time",
        "expired_time": "Expired Time",
    },
    "domain": {
        "inst_name": "Name",
        "organization": "Organization",
        "registration_date": "Registration Date",
        "expiration_time": "Expiration Time",
        "owner": "Owner",
    },
}

ASSOCIATION_TYPE = {
    "belong": "Belong",
    "group": "Group",
    "run": "Run",
    "install_on": "Install On",
    "contains": "Contains",
    "connect": "Connect",
}

ChangeRecordType = {
    "create_entity": "Create",
    "delete_entity": "Delete",
    "update_entity": "Update",
    "create_edge": "Create Association",
    "delete_edge": "Delete Association",
}

DEFAULT_ATTR = {
    "inst_name": "Name",
    "organization": "Organization",
}

LANGUAGE_DICT = {
    "CLASSIFICATION": CLASSIFICATION,
    "MODEL": MODEL,
    "ATTR": ATTR,
    "DEFAULT_ATTR": DEFAULT_ATTR,
    "ASSOCIATION_TYPE": ASSOCIATION_TYPE,
    "ChangeRecordType": ChangeRecordType,
}
