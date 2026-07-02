DANGEROUS_EXACT_COMMANDS = {"conf t", "write erase"}
DANGEROUS_COMMAND_PREFIXES = {
    "configure",
    "reload",
    "reboot",
    "reset",
    "delete",
    "erase",
    "format",
    "copy",
    "scp",
    "tftp",
    "ftp",
    "install",
    "upgrade",
    "commit",
    "save",
    "shutdown",
    "undo",
    "set",
}

SUPPORTED_DEVICE_TYPES = {"huawei", "hp_comware", "cisco_ios", "juniper_junos", "f5_tmsh", "fortinet"}

DEVICE_TYPE_DISABLE_PAGING = {
    "cisco_ios": "terminal length 0",
    "hp_comware": "screen-length disable",
    "huawei": "screen-length 0 temporary",
}

COMMAND_ERROR_PATTERNS = (
    "invalid input",
    "unknown command",
    "ambiguous command",
    "incomplete command",
    "unrecognized command",
)
