from ansible.cli.adhoc import AdHocCLI
from ansible.cli.playbook import PlaybookCLI


def run_embedded_ansible(cli_name: str, args: list[str]) -> int:
    forwarded_args = list(args)
    if forwarded_args and forwarded_args[0] == "--":
        forwarded_args = forwarded_args[1:]

    if cli_name == "adhoc":
        entry_args = ["ansible", *forwarded_args]
        try:
            AdHocCLI.cli_executor(entry_args)
        except SystemExit as exc:
            return int(exc.code or 0)
        return 0

    if cli_name == "playbook":
        entry_args = ["ansible-playbook", *forwarded_args]
        try:
            PlaybookCLI.cli_executor(entry_args)
        except SystemExit as exc:
            return int(exc.code or 0)
        return 0

    raise ValueError(f"unsupported embedded ansible cli: {cli_name}")
