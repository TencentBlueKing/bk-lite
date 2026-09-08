PHYSICAL_SERVER_MODEL_ID = "physcial_server"
PHYSICAL_SERVER_PROTOCOLS = frozenset({"ipmi", "redfish"})
DEFAULT_PHYSICAL_SERVER_PROTOCOL = "ipmi"


def normalize_physical_server_protocol(value) -> str:
    return str(value or DEFAULT_PHYSICAL_SERVER_PROTOCOL).strip().lower()


def resolve_physical_server_plugin_id(model_id, driver_type, protocol) -> str:
    if model_id != PHYSICAL_SERVER_MODEL_ID or driver_type != "protocol":
        return model_id
    normalized_protocol = normalize_physical_server_protocol(protocol)
    if normalized_protocol not in PHYSICAL_SERVER_PROTOCOLS:
        normalized_protocol = DEFAULT_PHYSICAL_SERVER_PROTOCOL
    return f"{PHYSICAL_SERVER_MODEL_ID}_{normalized_protocol}"
