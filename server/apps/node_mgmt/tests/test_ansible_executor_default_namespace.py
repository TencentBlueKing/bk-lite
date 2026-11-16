"""Default executors must never consume another node's local jobs."""
import json
import re
import unittest
from pathlib import Path


class AnsibleDefaultNamespaceTest(unittest.TestCase):
    def test_each_node_owns_its_task_namespace_and_dlq(self):
        path = Path(__file__).parents[1] / "support-files/collectors/Ansible-Executor.json"
        for definition in json.loads(path.read_text()):
            template = definition["default_config"]["nats"]
            namespaces = []
            for node in ["node-c", "node-d"]:
                rendered = template.replace("${node.id}", node)
                namespace = re.search(r'namespace: "([^"]+)"', rendered).group(1)
                dlq = re.search(r'dlq_subject: "([^"]+)"', rendered).group(1)
                self.assertIn(node, namespace)
                self.assertTrue(dlq.startswith(namespace + ".tasks."))
                namespaces.append(namespace)
            self.assertNotEqual(*namespaces)


if __name__ == "__main__":
    unittest.main()
