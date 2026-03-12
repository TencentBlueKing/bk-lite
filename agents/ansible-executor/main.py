import argparse
import asyncio
import os

from dotenv import load_dotenv

from core.config import load_config
from service.nats_service import AnsibleNATSService


def main() -> None:
    load_dotenv(".env")
    parser = argparse.ArgumentParser(description="ansible-executor service")
    parser.add_argument("--config", required=False, help="optional config file path")
    args = parser.parse_args()
    config = load_config(args.config)
    os.environ["ANSIBLE_WORK_DIR"] = config.ansible_work_dir
    asyncio.run(AnsibleNATSService(config).run())


if __name__ == "__main__":
    main()
