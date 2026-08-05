import argparse
import asyncio
import os

from core.config import load_config
from dotenv import load_dotenv
from service.nats_service import AnsibleNATSService
from service.runtime import configure_ansible_environment, find_config_path, find_dotenv_path, repair_ansible_windows_collection_layout


def main() -> None:
    configure_ansible_environment()
    collections_path = os.environ.get("ANSIBLE_COLLECTIONS_PATH")
    if collections_path:
        repair_ansible_windows_collection_layout(collections_path)
    dotenv_path = find_dotenv_path()
    if dotenv_path:
        load_dotenv(dotenv_path)
    parser = argparse.ArgumentParser(description="ansible-executor service")
    parser.add_argument(
        "--config",
        required=False,
        help="config file path; defaults to ./config.yml or executable-dir/config.yml",
    )
    parser.add_argument(
        "--internal-ansible-cli",
        choices=["adhoc", "playbook"],
        required=False,
        help="internal helper mode for embedded ansible execution",
    )
    parser.add_argument(
        "ansible_args",
        nargs=argparse.REMAINDER,
        help="arguments forwarded to embedded ansible helper",
    )
    args = parser.parse_args()
    if args.internal_ansible_cli:
        from service.embedded_ansible import run_embedded_ansible

        raise SystemExit(run_embedded_ansible(args.internal_ansible_cli, args.ansible_args))

    config = load_config(find_config_path(args.config))
    os.environ["ANSIBLE_WORK_DIR"] = config.ansible_work_dir
    asyncio.run(AnsibleNATSService(config).run())


if __name__ == "__main__":
    main()
