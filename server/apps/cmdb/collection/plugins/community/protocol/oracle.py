from apps.cmdb.collection.plugins.community.protocol.base import BaseProtocolCollectionPlugin


class OracleCollectionPlugin(BaseProtocolCollectionPlugin):
    supported_model_id = "oracle"
    metric_names = ("oracle_info_gauge", "oracle_instance_info_gauge", "oracle_pdb_info_gauge")

    @staticmethod
    def _belong_oracle(child_model, data):
        db_key = str(data.get("db_unique_name") or "").strip()
        if not db_key:
            return []
        return [
            {
                "model_id": "oracle",
                "inst_name": db_key,
                "asst_id": "belong",
                "model_asst_id": f"{child_model}_belong_oracle",
            }
        ]

    def asso_oracle_instance(self, data, *args, **kwargs):
        return self._belong_oracle("oracle_instance", data)

    def asso_oracle_pdb(self, data, *args, **kwargs):
        return self._belong_oracle("oracle_pdb", data)

    field_mappings = {
        "oracle": {
            "inst_name": "inst_name",
            "ip_addr": "ip_addr",
            "port": "port",
            "sid": "sid",
            "service_name": "service_name",
            "db_name": "db_name",
            "db_unique_name": "db_unique_name",
            "version": "version",
            "database_role": "database_role",
            "open_mode": "open_mode",
            "log_mode": "log_mode",
            "nls_characterset": "nls_characterset",
            "max_mem": "max_mem",
            "max_conn": "max_conn",
            "is_cdb": "is_cdb",
            "collect_scope": "collect_scope",
            "cluster_type": "cluster_type",
            "instance_count": "instance_count",
            "pdb_count": "pdb_count",
        },
        "oracle_instance": {
            "inst_name": "inst_name",
            "db_unique_name": "db_unique_name",
            "sid": "sid",
            "host_name": "host_name",
            "ip_addr": "ip_addr",
            "port": "port",
            "status": "status",
            "version": "version",
            "assos": asso_oracle_instance,
        },
        "oracle_pdb": {
            "inst_name": "inst_name",
            "db_unique_name": "db_unique_name",
            "pdb_name": "pdb_name",
            "open_mode": "open_mode",
            "restricted": "restricted",
            "service_name": "service_name",
            "assos": asso_oracle_pdb,
        },
    }
