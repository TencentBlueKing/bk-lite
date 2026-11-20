"""每个节点的默认 Ansible Executor 必须使用自己的任务队列。"""

import json
import re
from pathlib import Path


def test_each_node_owns_its_task_namespace_and_dlq():
    path = Path(__file__).parents[1] / "support-files/collectors/Ansible-Executor.json"
    definitions = json.loads(path.read_text(encoding="utf-8"))

    assert definitions
    for definition in definitions:
        template = definition["default_config"]["nats"]
        namespaces = []
        for node_id in ("node-c", "node-d"):
            rendered = template.replace("${node.id}", node_id)
            namespace = re.search(r'namespace: "([^"]+)"', rendered).group(1)
            dlq = re.search(r'dlq_subject: "([^"]+)"', rendered).group(1)
            assert namespace == f"bk.ans_exec.{node_id}"
            assert dlq == f"{namespace}.dlq"
            assert not dlq.startswith(f"{namespace}.tasks.")
            namespaces.append(namespace)
        assert namespaces[0] != namespaces[1]
