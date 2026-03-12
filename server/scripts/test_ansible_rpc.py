import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

from apps.rpc.ansible import AnsibleExecutor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test script for server/apps/rpc/ansible.py"
    )
    parser.add_argument(
        "--instance-id",
        default="default",
        help="ansible-executor NATS instance id (default: default)",
    )
    parser.add_argument(
        "--callback-subject",
        default="ansible.test.ansible_test_callback",
        help="callback subject (default: ansible.test.ansible_test_callback)",
    )
    parser.add_argument(
        "--skip-adhoc",
        action="store_true",
        help="skip adhoc submit test",
    )
    parser.add_argument(
        "--skip-playbook",
        action="store_true",
        help="skip playbook submit test",
    )
    parser.add_argument(
        "--skip-query",
        action="store_true",
        help="skip task query test",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=30,
        help="max polling seconds for task_query (default: 30)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="poll interval seconds for task_query (default: 2.0)",
    )
    return parser


def print_json(title: str, payload):
    print(f"\n[{title}]\n{json.dumps(payload, ensure_ascii=False, indent=2)}")


def submit_adhoc(executor: AnsibleExecutor, callback_subject: str):
    task_id = f"adhoc-{uuid.uuid4().hex[:10]}"
    callback = {"subject": callback_subject, "timeout": 10} if callback_subject else {}
    resp = executor.adhoc(
        inventory_content="localhost ansible_connection=local\n",
        hosts="localhost",
        module="ping",
        module_args="",
        extra_vars={},
        callback=callback,
        task_id=task_id,
        timeout=60,
    )
    print_json("adhoc submit response", resp)
    return task_id, resp


def submit_playbook(executor: AnsibleExecutor, callback_subject: str):
    task_id = f"playbook-{uuid.uuid4().hex[:10]}"
    callback = {"subject": callback_subject, "timeout": 10} if callback_subject else {}
    playbook_content = (
        "- hosts: all\n"
        "  gather_facts: false\n"
        "  tasks:\n"
        "    - name: rpc smoke test\n"
        "      ansible.builtin.debug:\n"
        '        msg: "hello from test_ansible_rpc.py"\n'
    )
    resp = executor.playbook(
        playbook_content=playbook_content,
        inventory_content="localhost ansible_connection=local\n",
        extra_vars={},
        callback=callback,
        task_id=task_id,
        timeout=120,
    )
    print_json("playbook submit response", resp)
    return task_id, resp


def poll_task(
    executor: AnsibleExecutor, task_id: str, poll_seconds: int, poll_interval: float
):
    deadline = time.time() + poll_seconds
    latest = None
    while time.time() < deadline:
        latest = executor.task_query(task_id=task_id, timeout=10)
        status = str(latest.get("status", ""))
        if status in {"success", "failed", "callback_failed"}:
            print_json(f"task query terminal: {task_id}", latest)
            return latest
        print_json(f"task query pending: {task_id}", latest)
        time.sleep(poll_interval)
    print_json(f"task query timeout: {task_id}", latest or {"task_id": task_id})
    return latest


def main():
    args = build_parser().parse_args()
    executor = AnsibleExecutor(instance_id=args.instance_id)
    task_ids = []

    if not args.skip_adhoc:
        task_id, _ = submit_adhoc(executor, args.callback_subject)
        task_ids.append(task_id)

    if not args.skip_playbook:
        task_id, _ = submit_playbook(executor, args.callback_subject)
        task_ids.append(task_id)

    if not args.skip_query:
        for task_id in task_ids:
            poll_task(executor, task_id, args.poll_seconds, args.poll_interval)


if __name__ == "__main__":
    main()
