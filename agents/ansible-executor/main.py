import argparse
import asyncio
import os

from dotenv import load_dotenv

from core.config import load_config
from service.embedded_ansible import run_embedded_ansible
from service.runtime import find_config_path, find_dotenv_path
from service.nats_service import AnsibleNATSService


def main() -> None:
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
        raise SystemExit(
            run_embedded_ansible(args.internal_ansible_cli, args.ansible_args)
        )

    config = load_config(find_config_path(args.config))
    os.environ["ANSIBLE_WORK_DIR"] = config.ansible_work_dir
    asyncio.run(AnsibleNATSService(config).run())


if __name__ == "__main__":
    main()
