from apps.rpc.node_mgmt import NodeMgmt


class FormatChildConfig:

    @staticmethod
    def collector(data):
        object_type = data["collect_type"]
        configs = data["configs"]
        instances = data["instances"]
        if object_type == "host":
            return FormatChildConfig.format_host(configs, instances)
        elif object_type == "ping":
            return FormatChildConfig.format_ping(instances, configs)
        elif object_type == "web":
            return FormatChildConfig.format_web(instances, configs)
        elif object_type == "trap":
            return FormatChildConfig.format_trap(instances, configs)
        elif object_type == "ipmi":
            return FormatChildConfig.format_ipmi(instances, configs)
        elif object_type == "snmp":
            return FormatChildConfig.format_snmp(instances, configs)
        elif object_type == "middleware":
            return FormatChildConfig.format_middleware(configs, instances)
        elif object_type == "docker":
            return FormatChildConfig.format_docker(instances, configs)
        elif object_type == "database":
            return FormatChildConfig.format_database(configs, instances)
        elif object_type == "vmware":
            return FormatChildConfig.format_vmware(configs, instances)
        else:
            raise ValueError(f"Unsupported object type: {object_type}")

    @staticmethod
    def format_vmware(configs, instances):
        result = {"object_type": "http", "nodes": []}

        for instance in instances:
            instance_id, instance_type = instance["instance_id"], instance["instance_type"]
            for node_id in instance["node_ids"]:
                node_info = {"id": node_id, "configs": []}
                for config in configs:
                    username, password = config.get("username", ""), config.get("password", "")
                    host = instance.get("host", "")
                    interval = config.get("interval", 60)
                    url = "${STARGAZER_URL}/api/monitor/vmware/metrics"
                    config_info = {
                        "type": config["type"],
                        "instance_id": instance_id,
                        "instance_type": instance_type,
                        "interval": interval,
                        "url": url,
                        "custom_headers": {"username":username, "password":password, "host":host},
                    }
                    node_info["configs"].append(config_info)

                result["nodes"].append(node_info)

        return result

    @staticmethod
    def format_database(configs, instances):
        result = {"object_type": "database", "nodes": []}

        for instance in instances:
            instance_id, instance_type = instance["instance_id"], instance["instance_type"]
            server = instance.get("server", "")
            host = instance.get("host", "")
            port = instance.get("port", "")
            for node_id in instance["node_ids"]:
                node_info = {"id": node_id, "configs": []}
                for config in configs:
                    username, password = config.get("username", ""), config.get("password", "")
                    interval = config.get("interval", 10)
                    config_info = {
                        "type": config["type"],
                        "instance_id": instance_id,
                        "instance_type": instance_type,
                        "interval": interval,
                        "server": server,
                        "host": host,
                        "port": port,
                        "username": username,
                        "password": password,
                    }
                    node_info["configs"].append(config_info)

                result["nodes"].append(node_info)

        return result

    @staticmethod
    def format_docker(instances, configs):
        result = {"object_type": "docker", "nodes": []}

        for instance in instances:
            instance_id, instance_type = instance["instance_id"], instance["instance_type"]

            endpoint = instance["endpoint"]

            for node_id in instance["node_ids"]:
                node_info = {"id": node_id, "configs": []}

                for config in configs:
                    interval = config.get("interval", 10)
                    node_info["configs"].append({
                        "type": config["type"],
                        "instance_id": instance_id,
                        "instance_type": instance_type,
                        "interval": interval,
                        "url": endpoint,
                    })

                result["nodes"].append(node_info)

        return result

    @staticmethod
    def format_middleware(configs, instances):
        result = {"object_type": "middleware", "nodes": []}

        for instance in instances:
            instance_id, instance_type = instance["instance_id"], instance["instance_type"]
            url = instance["url"]
            for node_id in instance["node_ids"]:
                node_info = {"id": node_id, "configs": []}
                for config in configs:
                    username, password, timeout = config.get("username", ""), config.get("password", ""), config.get("timeout")
                    interval = config.get("interval", 10)
                    config_info = {
                        "type": config["type"],
                        "instance_id": instance_id,
                        "instance_type": instance_type,
                        "interval": interval,
                        "url": url,
                        "username": username,
                        "password": password,
                    }
                    if timeout:
                        config_info["timeout"] = timeout
                    node_info["configs"].append(config_info)

                result["nodes"].append(node_info)

        return result

    @staticmethod
    def format_host(configs, instances):
        result = {"object_type": "host", "nodes": []}

        for instance in instances:
            instance_id, instance_type = instance["instance_id"], instance["instance_type"]
            for node_id in instance["node_ids"]:
                node_info = {"id": node_id, "configs": []}

                for config in configs:
                    interval = config.get("interval", 10)
                    node_info["configs"].append({
                        "type": config["type"],
                        "instance_id": instance_id,
                        "instance_type": instance_type,
                        "interval": interval,
                    })

                result["nodes"].append(node_info)

        return result

    @staticmethod
    def format_ping(instances, configs):
        result = {"object_type": "ping", "nodes": []}

        for instance in instances:
            instance_id, instance_type = instance["instance_id"], instance["instance_type"]
            url = instance["url"]

            for node_id in instance["node_ids"]:
                node_info = {"id": node_id, "configs": []}

                for config in configs:
                    interval = config.get("interval", 10)

                    node_info["configs"].append({
                        "type": config["type"],
                        "instance_id": instance_id,
                        "instance_type": instance_type,
                        "interval": interval,
                        "url": url,
                    })

                result["nodes"].append(node_info)

        return result

    @staticmethod
    def format_web(instances, configs):
        result = {"object_type": "web", "nodes": []}

        for instance in instances:
            instance_id, instance_type = instance["instance_id"], instance["instance_type"]
            url = instance["url"]

            for node_id in instance["node_ids"]:
                node_info = {"id": node_id, "configs": []}

                for config in configs:
                    interval = config.get("interval", 10)

                    node_info["configs"].append({
                        "type": config["type"],
                        "instance_id": instance_id,
                        "instance_type": instance_type,
                        "interval": interval,
                        "url": url,
                    })

                result["nodes"].append(node_info)

        return result

    @staticmethod
    def format_trap(instances, configs):
        result = {"object_type": "trap", "nodes": []}

        for instance in instances:
            instance_id, instance_type = instance["instance_id"], instance["instance_type"]

            for node_id in instance["node_ids"]:
                node_info = {"id": node_id, "configs": []}

                for config in configs:
                    interval = config.get("interval", 10)

                    node_info["configs"].append({
                        "type": config["type"],
                        "instance_id": instance_id,
                        "instance_type": instance_type,
                        "interval": interval,
                    })

                result["nodes"].append(node_info)

        return result

    @staticmethod
    def format_ipmi(instances, configs):
        result = {"object_type": "ipmi", "nodes": []}

        for instance in instances:
            instance_id, instance_type = instance["instance_id"], instance["instance_type"]
            ip = instance["ip"]

            for node_id in instance["node_ids"]:
                node_info = {"id": node_id, "configs": []}

                for config in configs:
                    interval = config.get("interval", 10)

                    node_info["configs"].append({
                        "type": config["type"],
                        "instance_id": instance_id,
                        "instance_type": instance_type,
                        "interval": interval,
                        "server": f"{config['username']}:{config['password']}@{config['protocol']}({ip})",
                    })

                result["nodes"].append(node_info)

        return result

    @staticmethod
    def format_snmp(instances, configs):
        result = {"object_type": "snmp", "nodes": []}

        for instance in instances:
            instance_id, instance_type = instance["instance_id"], instance["instance_type"]
            ip = instance["ip"]

            for node_id in instance["node_ids"]:
                node_info = {"id": node_id, "configs": []}
                for config in configs:
                    interval = config.get("interval", 10)

                    snmp_config = FormatChildConfig.format_snmp_config(dict(ip=ip, **config))
                    node_info["configs"].append({
                        "type": config["type"],
                        "instance_id": instance_id,
                        "instance_type": instance_type,
                        "interval": interval,
                        "snmp_config": snmp_config,
                    })

                result["nodes"].append(node_info)

        return result

    @staticmethod
    def format_snmp_config(config):
        if config["version"] == 2:
            result = f"""agents = ["udp://{config['ip']}:{config['port']}"]
    version = 2
    community= "{config['community']}"
    timeout = "{config['timeout']}" """
        elif config["version"] == 3:
            result = f"""agents = ["udp://{config['ip']}:{config['port']}"]
    version = 3
    timeout = "{config['timeout']}"
    sec_name = "{config['sec_name']}"                 # SNMPv3 用户名
    sec_level = "{config['sec_level']}"             # 安全级别：authPriv (认证 + 加密)
    auth_protocol = "{config['auth_protocol']}"              # 认证协议：SHA
    auth_password = "{config['auth_password']}"       # 认证密码
    priv_protocol = "{config['priv_protocol']}"              # 加密协议：AES
    priv_password = "{config['priv_password']}"       # 加密密码 """
        else:
            raise ValueError("SNMP version error")
        return result


class NodeUtils:

    @staticmethod
    def get_nodes(query_data: dict):
        return NodeMgmt().node_list(query_data)

    @staticmethod
    def batch_setting_node_child_config(data: dict):
        return NodeMgmt().batch_setting_node_child_config(data)

    @staticmethod
    def get_instance_child_config(query_data: dict):
        return NodeMgmt().get_instance_child_config(query_data)

    @staticmethod
    def update_instance_child_config(data: dict):
        return NodeMgmt().update_instance_child_config(data)

    @staticmethod
    def delete_instance_child_config(instance_ids: list):
        return NodeMgmt().delete_instance_child_config(instance_ids)
