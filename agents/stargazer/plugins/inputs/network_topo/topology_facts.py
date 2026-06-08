from plugins.inputs.network_topo.protocol_oids import PROTOCOL_OID_GROUPS

PROTOCOL_PRECEDENCE = {
    "lldp": 0,
    "cdp": 1,
    "fdb": 2,
    "arp": 3,
}


def get_protocol_default_confidence(protocol):
    return PROTOCOL_OID_GROUPS.get(protocol, {}).get("default_confidence", 0.5)


def get_protocol_precedence(protocol):
    return PROTOCOL_PRECEDENCE.get(protocol, len(PROTOCOL_PRECEDENCE))


def build_topology_fact(protocol, observation, raw_evidence=None, confidence=None):
    evidence = raw_evidence if raw_evidence is not None else observation.get("raw_evidence")
    return {
        "source_protocol": protocol,
        "confidence": get_protocol_default_confidence(protocol) if confidence is None else confidence,
        "local_device_id": observation.get("local_device_id"),
        "local_port_id": observation.get("local_port_id"),
        "local_port_name": observation.get("local_port_name"),
        "remote_device_id": observation.get("remote_device_id"),
        "remote_port_id": observation.get("remote_port_id"),
        "remote_port_name": observation.get("remote_port_name"),
        "raw_evidence": evidence,
    }


def get_topology_fact_edge_key(fact):
    return (
        fact.get("local_device_id"),
        fact.get("local_port_id"),
        fact.get("remote_device_id"),
        fact.get("remote_port_id"),
    )


def get_topology_fact_rank(fact, position=0):
    confidence = fact.get("confidence")
    normalized_confidence = confidence if confidence is not None else 0
    return (
        -normalized_confidence,
        get_protocol_precedence(fact.get("source_protocol")),
        position,
    )


def merge_topology_facts(facts):
    merged_facts = []
    merged_fact_indexes = {}
    best_fact_ranks = {}
    for position, fact in enumerate(facts):
        edge_key = get_topology_fact_edge_key(fact)
        rank = get_topology_fact_rank(fact, position)
        existing_index = merged_fact_indexes.get(edge_key)
        if existing_index is None:
            merged_fact_indexes[edge_key] = len(merged_facts)
            best_fact_ranks[edge_key] = rank
            merged_facts.append(fact)
            continue
        if rank < best_fact_ranks[edge_key]:
            best_fact_ranks[edge_key] = rank
            merged_facts[existing_index] = fact
    return merged_facts


def build_topology_facts(protocol, observations):
    return [
        build_topology_fact(
            protocol,
            observation,
            raw_evidence=observation.get("raw_evidence"),
            confidence=observation.get("confidence"),
        )
        for observation in observations
    ]
