from __future__ import annotations

import unittest

import pytest

from apps.cmdb.collection.collect_plugin.topology.models import NormalizedPort
from apps.cmdb.collection.collect_plugin.topology.parse import (
    build_multi_vlan_corroboration_summary,
    extract_previous_links,
    parse_aggregate_result,
    resolve_local_neighbor_port_id,
)

pytestmark = [pytest.mark.unit]


class ParseTopologyTest(unittest.TestCase):
    def test_authoritative_neighbor_link_uses_bridge_port_resolution(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "10", "val": "Gi1/0/1"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "10", "val": "0xaaaaaaaaaaaa"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.5.1", "val": "sw2"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.5.1", "val": "Gi1/0/2"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.5.1", "val": "5"},
                                    {"tag": "LLDP-RemChassisId", "ifindex": "0.5.1", "val": "sw2"},
                                    {"tag": "LLDP-LocPortId", "ifindex": "5", "val": "Gi1/0/1"},
                                ],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "5", "val": "10"}],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "2", "val": "Gi1/0/2"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 1)
        self.assertEqual(result["relationships"][0]["relationship_type"], "authoritative")
        self.assertEqual(result["topology"]["authoritative_links"][0]["source_port_id"], "sw1:10")

    def test_lldp_mac_subtype_decodes_mac_port_identifier(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "1", "val": "Gi1/0/1"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xaaaaaaaaaaaa"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "sw2"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.1", "val": "0xbbbbbbbbbbbb"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.1", "val": "3"},
                                    {"tag": "LLDP-RemChassisId", "ifindex": "0.1.1", "val": "sw2"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                }
            ]
        }

        result = parse_aggregate_result(aggregate)
        observation = result["normalized"]["neighbor_observations"][0]
        self.assertEqual(observation["remote_port_id"], "bb:bb:bb:bb:bb:bb")

    def test_cdp_address_is_normalized_for_target_resolution(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "CDP-DeviceId", "ifindex": "1.1", "val": "sw2"},
                                    {"tag": "CDP-DevicePort", "ifindex": "1.1", "val": "Eth2"},
                                    {"tag": "CDP-AddressType", "ifindex": "1.1", "val": "1"},
                                    {"tag": "CDP-Address", "ifindex": "1.1", "val": "1.10.0.0.2"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "2", "val": "Eth2"}],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.0.0.2", "val": "10.0.0.2"}],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 1)
        self.assertEqual(result["topology"]["authoritative_links"][0]["target_device"], "sw2")

    def test_lldp_remote_chassis_mac_can_resolve_target_device(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "HUAWEI"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.1", "val": "Eth2"},
                                    {"tag": "LLDP-RemPortDesc", "ifindex": "0.1.1", "val": "Eth2"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.1", "val": "5"},
                                    {"tag": "LLDP-RemChassisIdSubtype", "ifindex": "0.1.1", "val": "4"},
                                    {"tag": "LLDP-RemChassisId", "ifindex": "0.1.1", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "10.0.0.2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": ""}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "2", "val": "Eth2"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 1)
        self.assertEqual(result["topology"]["authoritative_links"][0]["target_device"], "10.0.0.2")
        self.assertEqual(result["topology"]["authoritative_links"][0]["target_port_id"], "10.0.0.2:2")

    def test_lldp_remote_port_can_recover_device_resolution_for_single_device_shared_chassis_mac(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "HUAWEI"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.1", "val": "GigabitEthernet0/0/3"},
                                    {"tag": "LLDP-RemPortDesc", "ifindex": "0.1.1", "val": "GigabitEthernet0/0/3"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.1", "val": "5"},
                                    {"tag": "LLDP-RemChassisIdSubtype", "ifindex": "0.1.1", "val": "4"},
                                    {"tag": "LLDP-RemChassisId", "ifindex": "0.1.1", "val": "0x085c1bc92016"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "10.0.0.2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": ""}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "2", "val": "GigabitEthernet0/0/3"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0x085c1bc92016"},
                                    {"tag": "IFXTable-IfName", "ifindex": "3", "val": "GigabitEthernet0/0/4"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "3", "val": "0x085c1bc92016"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 1)
        self.assertEqual(result["summary"]["unresolved_neighbors"], 0)
        self.assertEqual(result["topology"]["authoritative_links"][0]["target_device"], "10.0.0.2")
        self.assertEqual(result["topology"]["authoritative_links"][0]["target_port_id"], "10.0.0.2:2")

    def test_lldp_local_port_id_fallback_resolves_interface(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "10", "val": "Gi1/0/1"},
                                    {"tag": "IFTable-IfDescr", "ifindex": "10", "val": "Gi1/0/1"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.77.1", "val": "sw2"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.77.1", "val": "Gi1/0/2"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.77.1", "val": "5"},
                                    {"tag": "LLDP-RemChassisId", "ifindex": "0.77.1", "val": "sw2"},
                                    {"tag": "LLDP-LocPortId", "ifindex": "77", "val": "Gi1/0/1"},
                                    {"tag": "LLDP-LocPortIdSubtype", "ifindex": "77", "val": "5"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                }
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["unresolved_neighbors"], 1)
        self.assertEqual(result["normalized"]["neighbor_observations"][0]["local_port_id"], "sw1:10")

    def test_neighbor_with_resolved_device_but_unresolved_port_stays_unresolved(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "sw2"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.1", "val": "NotARealPort"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.1", "val": "5"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "2", "val": "Eth2"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 0)
        self.assertEqual(result["summary"]["unresolved_neighbors"], 1)
        self.assertEqual(result["topology"]["unresolved_neighbors"][0]["resolution_state"], "resolved_device_only")

    def test_neighbor_confidence_depends_on_identifier_quality(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "sw2"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.1", "val": "Eth2"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.1", "val": "5"},
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.2", "val": "sw2"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.2", "val": "0x020000000001"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.2", "val": "4"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "2", "val": "Eth2"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 1)

    def test_remote_port_name_normalization_matches_gigabitethernet_to_gi(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "sw2"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.1", "val": "GigabitEthernet0/0/5"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.1", "val": "5"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "2", "val": "Gi0/0/5"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 1)
        self.assertEqual(result["topology"]["authoritative_links"][0]["target_port_id"], "sw2:2")

    def test_remote_port_name_normalization_matches_port_channel_to_po(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "sw2"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.1", "val": "Port-Channel1"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.1", "val": "5"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "2", "val": "Po1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 1)
        self.assertEqual(result["topology"]["authoritative_links"][0]["target_port_id"], "sw2:2")

    def test_remote_port_name_normalization_matches_ethernet_to_eth(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "sw2"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.1", "val": "Ethernet1/0/8"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.1", "val": "5"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "2", "val": "Eth1/0/8"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 1)
        self.assertEqual(result["topology"]["authoritative_links"][0]["target_port_id"], "sw2:2")

    def test_remote_port_name_normalization_matches_tengigabitethernet_to_te(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "sw2"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.1", "val": "TenGigabitEthernet1/0/1"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.1", "val": "5"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "2", "val": "Te1/0/1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 1)
        self.assertEqual(result["topology"]["authoritative_links"][0]["target_port_id"], "sw2:2")

    def test_remote_port_name_normalization_does_not_fuzzily_match_prefixes(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "sw2"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.1", "val": "Gi1"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.1", "val": "5"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "2", "val": "Gi1/0/1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 0)
        self.assertEqual(result["summary"]["unresolved_neighbors"], 1)
        self.assertEqual(result["topology"]["unresolved_neighbors"][0]["resolution_state"], "resolved_device_only")

    def test_fdp_neighbor_produces_authoritative_link(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "10", "val": "1/1/1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "FDP-DeviceId", "ifindex": "10.1", "val": "sw2"},
                                    {"tag": "FDP-DevicePort", "ifindex": "10.1", "val": "1/1/2"},
                                    {"tag": "FDP-Platform", "ifindex": "10.1", "val": "Brocade"},
                                    {"tag": "FDP-Version", "ifindex": "10.1", "val": "7.x"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "2", "val": "1/1/2"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 1)
        link = result["topology"]["authoritative_links"][0]
        self.assertEqual(link["evidence_source"], "fdp")
        self.assertEqual(link["source_port_id"], "sw1:10")
        self.assertEqual(link["target_port_id"], "sw2:2")

    def test_fdp_neighbor_without_remote_port_keeps_unresolved_neighbor(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "10", "val": "1/1/1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "FDP-DeviceId", "ifindex": "10.1", "val": "sw2"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "2", "val": "1/1/2"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 0)
        self.assertEqual(result["summary"]["unresolved_neighbors"], 1)
        self.assertEqual(result["topology"]["unresolved_neighbors"][0]["resolution_state"], "resolved_device_only")

    def test_fdp_neighbor_with_missing_local_port_keeps_unresolved_neighbor(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "10", "val": "1/1/1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "FDP-DeviceId", "ifindex": "99.1", "val": "sw2"},
                                    {"tag": "FDP-DevicePort", "ifindex": "99.1", "val": "1/1/2"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                }
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 0)
        self.assertEqual(result["summary"]["unresolved_neighbors"], 1)
        self.assertEqual(result["topology"]["unresolved_neighbors"][0]["resolution_state"], "unresolved_local_port")
        unresolved = result["topology"]["unresolved_neighbors"]
        confidences = sorted(item["confidence"] for item in unresolved)
        self.assertEqual(confidences, [20])

    def test_fdb_port_zero_is_ignored(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [{"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xaaaaaaaaaaaa"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "5", "val": "1"}],
                                "fdb": [
                                    {"tag": "FDB-Port", "ifindex": "170.170.170.170.170.170", "val": "0"},
                                    {"tag": "FDB-Status", "ifindex": "170.170.170.170.170.170", "val": "3"},
                                ],
                            }
                        }
                    },
                }
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["normalized"]["fdb_observations"], [])

    def test_fdb_non_learned_status_is_not_promoted_to_link(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [{"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xaaaaaaaaaaaa"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "5", "val": "1"}],
                                "fdb": [
                                    {"tag": "FDB-Port", "ifindex": "187.187.187.187.187.187", "val": "5"},
                                    {"tag": "FDB-Status", "ifindex": "187.187.187.187.187.187", "val": "2"},
                                ],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [{"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["inferred_links"], 0)

    def test_qbridge_vlan_is_carried_into_inferred_fdb_link(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [{"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xaaaaaaaaaaaa"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "5", "val": "1"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "100.187.187.187.187.187.187", "val": "5"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "100.187.187.187.187.187.187", "val": "3"},
                                ],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [{"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        inferred = result["topology"]["inferred_links"][0]
        self.assertEqual(inferred["evidence_source"], "fdb")
        self.assertEqual(inferred["vlan"], "100")
        self.assertEqual(inferred["confidence"], 75)
        self.assertEqual(inferred["relationship_id"], "inf:sw1:1:sw2:2:fdb:100")

    def test_same_endpoint_pair_with_different_vlans_is_not_collapsed(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [{"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xaaaaaaaaaaaa"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "5", "val": "1"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "100.187.187.187.187.187.187", "val": "5"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "100.187.187.187.187.187.187", "val": "3"},
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "200.187.187.187.187.187.187", "val": "5"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "200.187.187.187.187.187.187", "val": "3"},
                                ],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [{"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        inferred_links = result["topology"]["inferred_links"]
        self.assertEqual(len(inferred_links), 2)
        self.assertEqual(sorted(link["vlan"] for link in inferred_links), ["100", "200"])
        self.assertEqual(sorted(link["relationship_id"] for link in inferred_links), [
            "inf:sw1:1:sw2:2:fdb:100",
            "inf:sw1:1:sw2:2:fdb:200",
        ])
        summary = result["topology"]["multi_vlan_corroboration_summary"]
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["vlan_ids"], ["100", "200"])
        self.assertEqual(summary[0]["evidence_count"], 2)

    def test_fdb_without_vlan_uses_lower_confidence_fallback(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [{"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xaaaaaaaaaaaa"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "5", "val": "1"}],
                                "fdb": [
                                    {"tag": "FDB-Port", "ifindex": "187.187.187.187.187.187", "val": "5"},
                                    {"tag": "FDB-Status", "ifindex": "187.187.187.187.187.187", "val": "3"},
                                ],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [{"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        inferred = result["topology"]["inferred_links"][0]
        self.assertIsNone(inferred["vlan"])
        self.assertEqual(inferred["confidence"], 60)
        self.assertIn("mac_only_fallback", inferred["provenance"][0]["signals"])

    def test_shared_mac_across_multiple_ports_does_not_create_inferred_target_port(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"}],
                                "ip": [],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.0.0.2", "val": "1"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.0.0.2", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "2", "val": "Eth2"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"},
                                    {"tag": "IFXTable-IfName", "ifindex": "3", "val": "Eth3"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "3", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["inferred_links"], 0)

    def test_vlan_interface_mac_is_not_used_as_inferred_target_port(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"}],
                                "ip": [],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.0.0.2", "val": "1"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.0.0.2", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "718", "val": "Vlan-interface69"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "718", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["inferred_links"], 0)

    def test_bidirectional_fdb_and_mutual_arp_promotes_high_confidence_inferred_link(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw247"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw247"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "9", "val": "GigabitEthernet0/0/4"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "9", "val": "0x085c1bc92099"},
                                    {"tag": "IFXTable-IfName", "ifindex": "18", "val": "Vlanif69"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "18", "val": "0x085c1bc92016"},
                                ],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.10.69.247", "val": "10.10.69.247"}],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.10.69.246", "val": "18"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.10.69.246", "val": "0x1090faf0918c"},
                                ],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "9", "val": "9"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "69.16.144.250.240.145.140", "val": "9"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "69.16.144.250.240.145.140", "val": "3"},
                                ],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw246"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw246"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "8", "val": "GigabitEthernet1/0/8"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "8", "val": "0x1090faf0918c"},
                                    {"tag": "IFXTable-IfName", "ifindex": "718", "val": "Vlan-interface69"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "718", "val": "0x1090faf0916a"},
                                ],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.10.69.246", "val": "10.10.69.246"}],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.10.69.247", "val": "718"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.10.69.247", "val": "0x085c1bc92099"},
                                ],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "8", "val": "8"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "69.8.92.27.201.32.153", "val": "8"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "69.8.92.27.201.32.153", "val": "3"},
                                ],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["inferred_links"], 1)
        inferred = result["topology"]["inferred_links"][0]
        self.assertEqual(inferred["evidence_source"], "fdb+arp")
        self.assertEqual(inferred["confidence"], 95)
        self.assertEqual({inferred["source_port_id"], inferred["target_port_id"]}, {"sw246:8", "sw247:9"})
        signals = inferred["provenance"][0]["signals"]
        self.assertIn("bidirectional_fdb", signals)
        self.assertIn("mutual_arp_visibility", signals)

    def test_authoritative_link_suppresses_bidirectional_fdb_arp_candidate(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw247"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw247"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "9", "val": "GigabitEthernet0/0/4"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "9", "val": "0x085c1bc92016"},
                                    {"tag": "IFXTable-IfName", "ifindex": "18", "val": "Vlanif69"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "18", "val": "0x085c1bc92016"},
                                ],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.10.69.247", "val": "10.10.69.247"}],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.10.69.246", "val": "18"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.10.69.246", "val": "0x1090faf0916a"},
                                ],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "9", "val": "9"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "69.16.144.250.240.145.106", "val": "9"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "69.16.144.250.240.145.106", "val": "3"},
                                ],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw246"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw246"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "8", "val": "GigabitEthernet1/0/8"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "8", "val": "0x1090faf0918c"},
                                    {"tag": "IFXTable-IfName", "ifindex": "718", "val": "Vlan-interface69"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "718", "val": "0x1090faf0916a"},
                                    {"tag": "LLDP-LocPortId", "ifindex": "1", "val": "GigabitEthernet1/0/8"},
                                    {"tag": "LLDP-LocPortIdSubtype", "ifindex": "1", "val": "5"},
                                ],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.10.69.246", "val": "10.10.69.246"}],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.10.69.247", "val": "718"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.10.69.247", "val": "0x085c1bc92016"},
                                ],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "sw247"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.1", "val": "GigabitEthernet0/0/4"},
                                    {"tag": "LLDP-RemPortDesc", "ifindex": "0.1.1", "val": "GigabitEthernet0/0/4"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.1", "val": "5"},
                                ],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "1", "val": "8"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "69.8.92.27.201.32.22", "val": "8"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "69.8.92.27.201.32.22", "val": "3"},
                                ],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 1)
        self.assertEqual(result["summary"]["inferred_links"], 0)
        self.assertEqual(result["topology"]["authoritative_links"][0]["evidence_source"], "lldp")

    def test_bidirectional_fdb_arp_does_not_promote_access_devices_seen_via_shared_uplink(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw247"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw247"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "9", "val": "GigabitEthernet0/0/4"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "9", "val": "0x085c1bc92016"},
                                    {"tag": "IFXTable-IfName", "ifindex": "10", "val": "GigabitEthernet0/0/5"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "10", "val": "0x085c1bc92016"},
                                    {"tag": "IFXTable-IfName", "ifindex": "18", "val": "Vlanif69"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "18", "val": "0x085c1bc92016"},
                                ],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.10.69.247", "val": "10.10.69.247"}],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.10.69.245", "val": "18"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.10.69.245", "val": "0x78a13eaf1308"},
                                    {"tag": "ARP-IfIndex", "ifindex": "10.10.69.248", "val": "18"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.10.69.248", "val": "0x588b1c65028a"},
                                ],
                                "neighbors": [],
                                "bridge": [
                                    {"tag": "BRIDGE-BasePortIfIndex", "ifindex": "9", "val": "9"},
                                    {"tag": "BRIDGE-BasePortIfIndex", "ifindex": "10", "val": "10"},
                                ],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "69.120.161.62.175.19.8", "val": "9"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "69.120.161.62.175.19.8", "val": "3"},
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "69.88.139.28.101.2.138", "val": "10"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "69.88.139.28.101.2.138", "val": "3"},
                                ],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw245"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw245"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "8", "val": "Ethernet1/0/8"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "8", "val": "0x78a13eaf1308"},
                                    {"tag": "IFXTable-IfName", "ifindex": "13", "val": "Vlan-interface69"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "13", "val": "0x78a13eaf131a"},
                                ],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.10.69.245", "val": "10.10.69.245"}],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.10.69.247", "val": "13"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.10.69.247", "val": "0x085c1bc92016"},
                                    {"tag": "ARP-IfIndex", "ifindex": "10.10.69.248", "val": "13"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.10.69.248", "val": "0x588b1c65028a"},
                                ],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "8", "val": "8"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "69.8.92.27.201.32.22", "val": "8"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "69.8.92.27.201.32.22", "val": "3"},
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "69.88.139.28.101.2.138", "val": "8"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "69.88.139.28.101.2.138", "val": "3"},
                                ],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw248"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw248"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "1", "val": "GigabitEthernet1"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0x588b1c65028a"},
                                    {"tag": "IFXTable-IfName", "ifindex": "100068", "val": "Vlan68"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "100068", "val": "0x588b1c65028a"},
                                ],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.10.69.248", "val": "10.10.69.248"}],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.10.69.247", "val": "100068"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.10.69.247", "val": "0x085c1bc92016"},
                                    {"tag": "ARP-IfIndex", "ifindex": "10.10.69.245", "val": "100068"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.10.69.245", "val": "0x78a13eaf1308"},
                                ],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "1", "val": "1"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "69.8.92.27.201.32.22", "val": "1"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "69.8.92.27.201.32.22", "val": "3"},
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "69.8.92.27.201.32.22", "val": "1"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "69.8.92.27.201.32.22", "val": "3"},
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "69.120.161.62.175.19.8", "val": "1"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "69.120.161.62.175.19.8", "val": "3"},
                                ],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        promoted_pairs = {
            frozenset({item["source_device"], item["target_device"]})
            for item in result["topology"]["inferred_links"]
            if item["evidence_source"] == "fdb+arp"
        }
        self.assertNotIn(frozenset({"sw245", "sw248"}), promoted_pairs)

    def test_shared_device_mac_is_not_used_as_unique_device_identity(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "Unknown"},
                                    {"tag": "LLDP-RemChassisIdSubtype", "ifindex": "0.1.1", "val": "4"},
                                    {"tag": "LLDP-RemChassisId", "ifindex": "0.1.1", "val": "0xbbbbbbbbbbbb"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.1", "val": "Eth2"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.1", "val": "5"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "2", "val": "Eth2"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw3"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw3"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "3", "val": "Eth3"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "3", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["authoritative_links"], 0)
        self.assertEqual(result["summary"]["unresolved_neighbors"], 1)
        self.assertEqual(result["topology"]["unresolved_neighbors"][0]["resolution_state"], "unresolved_remote")

    def test_shared_mac_across_two_devices_does_not_promote_bidirectional_fdb_arp(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xaaaaaaaaaaaa"},
                                ],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.0.0.1", "val": "10.0.0.1"}],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.0.0.2", "val": "1"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.0.0.2", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "1", "val": "1"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "100.187.187.187.187.187.187", "val": "1"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "100.187.187.187.187.187.187", "val": "3"},
                                ],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "2", "val": "Eth2"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.0.0.2", "val": "10.0.0.2"}],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.0.0.1", "val": "2"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.0.0.1", "val": "0xaaaaaaaaaaaa"},
                                ],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "2", "val": "2"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "100.170.170.170.170.170.170", "val": "2"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "100.170.170.170.170.170.170", "val": "3"},
                                ],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw3"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw3"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "3", "val": "Eth3"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "3", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        promoted_pairs = {
            frozenset({item["source_device"], item["target_device"]})
            for item in result["topology"]["inferred_links"]
            if item["evidence_source"] == "fdb+arp"
        }
        self.assertNotIn(frozenset({"sw1", "sw2"}), promoted_pairs)

    def test_duplicate_physical_mac_within_device_does_not_promote_bidirectional_fdb_arp(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xaaaaaaaaaaaa"},
                                    {"tag": "IFXTable-IfName", "ifindex": "2", "val": "Eth2"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xaaaaaaaaaaaa"},
                                ],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.0.0.1", "val": "10.0.0.1"}],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.0.0.2", "val": "1"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.0.0.2", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "1", "val": "1"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "100.187.187.187.187.187.187", "val": "1"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "100.187.187.187.187.187.187", "val": "3"},
                                ],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "2", "val": "Eth2"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.0.0.2", "val": "10.0.0.2"}],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.0.0.1", "val": "2"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.0.0.1", "val": "0xaaaaaaaaaaaa"},
                                ],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "2", "val": "2"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "100.170.170.170.170.170.170", "val": "2"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "100.170.170.170.170.170.170", "val": "3"},
                                ],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        promoted_pairs = {
            frozenset({item["source_device"], item["target_device"]})
            for item in result["topology"]["inferred_links"]
            if item["evidence_source"] == "fdb+arp"
        }
        self.assertNotIn(frozenset({"sw1", "sw2"}), promoted_pairs)

    def test_duplicate_physical_mac_within_device_promotes_when_fdb_is_stable_on_one_port(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw247"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw247"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "9", "val": "GigabitEthernet0/0/4"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "9", "val": "0x085c1bc92016"},
                                    {"tag": "IFXTable-IfName", "ifindex": "10", "val": "GigabitEthernet0/0/5"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "10", "val": "0x085c1bc92016"},
                                    {"tag": "IFXTable-IfName", "ifindex": "18", "val": "Vlanif69"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "18", "val": "0x085c1bc92016"},
                                ],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.10.69.247", "val": "10.10.69.247"}],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.10.69.246", "val": "18"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.10.69.246", "val": "0x1090faf0916a"},
                                ],
                                "neighbors": [],
                                "bridge": [
                                    {"tag": "BRIDGE-BasePortIfIndex", "ifindex": "9", "val": "9"},
                                    {"tag": "BRIDGE-BasePortIfIndex", "ifindex": "10", "val": "10"},
                                ],
                                "fdb": [
                                    {"tag": "FDB-Port", "ifindex": "16.144.250.240.145.106", "val": "9"},
                                    {"tag": "FDB-Status", "ifindex": "16.144.250.240.145.106", "val": "3"},
                                ],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw246"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw246"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "8", "val": "GigabitEthernet1/0/8"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "8", "val": "0x1090faf0916a"},
                                    {"tag": "IFXTable-IfName", "ifindex": "718", "val": "Vlan-interface69"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "718", "val": "0x1090faf0916a"},
                                ],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.10.69.246", "val": "10.10.69.246"}],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.10.69.247", "val": "718"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.10.69.247", "val": "0x085c1bc92016"},
                                ],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "8", "val": "8"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "69.8.92.27.201.32.22", "val": "8"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "69.8.92.27.201.32.22", "val": "3"},
                                    {"tag": "FDB-Port", "ifindex": "8.92.27.201.32.22", "val": "8"},
                                    {"tag": "FDB-Status", "ifindex": "8.92.27.201.32.22", "val": "3"},
                                ],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        promoted_pairs = {
            frozenset({item["source_device"], item["target_device"]})
            for item in result["topology"]["inferred_links"]
            if item["evidence_source"] == "fdb+arp"
        }
        self.assertIn(frozenset({"sw246", "sw247"}), promoted_pairs)

    def test_vlan_specific_fdb_link_missing_in_current_snapshot_is_marked_stale(self) -> None:
        current = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [{"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xaaaaaaaaaaaa"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "5", "val": "1"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "100.187.187.187.187.187.187", "val": "5"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "100.187.187.187.187.187.187", "val": "3"},
                                ],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [{"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }
        previous_links = [
            {
                "relationship_id": "inf:sw1:1:sw2:2:fdb:200",
                "relationship_type": "inferred",
                "evidence_source": "fdb",
                "confidence": 75,
                "source_device": "sw1",
                "source_port_id": "sw1:1",
                "source_inst_name": "sw1-sw1:1",
                "target_device": "sw2",
                "target_port_id": "sw2:2",
                "target_inst_name": "sw2-sw2:2",
                "remote_device_name": "sw2",
                "remote_port_name": "sw2:2",
                "vlan": "200",
            }
        ]

        result = parse_aggregate_result(current, previous_links=previous_links)
        self.assertEqual(result["summary"]["stale_links"], 1)
        self.assertEqual(result["topology"]["stale_links"][0]["vlan"], "200")
        self.assertEqual(result["topology"]["stale_links"][0]["status"], "stale")

    def test_authoritative_link_gets_multi_vlan_corroboration_summary_from_supporting_fdb(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xaaaaaaaaaaaa"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "sw2"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.1", "val": "Eth2"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.1", "val": "5"},
                                ],
                                "bridge": [{"tag": "BRIDGE-BasePortIfIndex", "ifindex": "5", "val": "1"}],
                                "fdb": [
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "100.187.187.187.187.187.187", "val": "5"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "100.187.187.187.187.187.187", "val": "3"},
                                    {"tag": "QBRIDGE-FdbPort", "ifindex": "200.187.187.187.187.187.187", "val": "5"},
                                    {"tag": "QBRIDGE-FdbStatus", "ifindex": "200.187.187.187.187.187.187", "val": "3"},
                                ],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "2", "val": "Eth2"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        summary = result["topology"]["multi_vlan_corroboration_summary"]
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["relationship_type"], "authoritative")
        self.assertEqual(summary[0]["vlan_ids"], ["100", "200"])

    def test_multi_vlan_summary_deduplicates_same_vlan_supporting_entries_in_count(self) -> None:
        current_links = [
            {
                "relationship_id": "inf:sw1:1:sw2:2:fdb:100",
                "relationship_type": "inferred",
                "evidence_source": "fdb",
                "confidence": 75,
                "source_device": "sw1",
                "source_port_id": "sw1:1",
                "source_inst_name": "sw1-Eth1",
                "target_device": "sw2",
                "target_port_id": "sw2:2",
                "target_inst_name": "sw2-Eth2",
                "remote_device_name": "sw2",
                "remote_port_name": "Eth2",
                "vlan": "100",
                "supporting_evidence": [
                    {
                        "relationship_id": "inf:sw1:1:sw2:2:fdb:100",
                        "evidence_source": "fdb",
                        "vlan": "100",
                        "disposition": "corroborating",
                    }
                ],
            },
            {
                "relationship_id": "inf:sw1:1:sw2:2:fdb:200",
                "relationship_type": "inferred",
                "evidence_source": "fdb",
                "confidence": 75,
                "source_device": "sw1",
                "source_port_id": "sw1:1",
                "source_inst_name": "sw1-Eth1",
                "target_device": "sw2",
                "target_port_id": "sw2:2",
                "target_inst_name": "sw2-Eth2",
                "remote_device_name": "sw2",
                "remote_port_name": "Eth2",
                "vlan": "200",
                "supporting_evidence": [],
            },
        ]

        summary = build_multi_vlan_corroboration_summary(current_links, [])
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["vlan_ids"], ["100", "200"])
        self.assertEqual(summary[0]["evidence_count"], 2)

    def test_previous_snapshot_missing_link_is_marked_stale(self) -> None:
        # Rewritten: instead of writing files, construct previous_links dict directly
        # and pass it to parse_aggregate_result via extract_previous_links + previous_links=.
        current = {"devices": []}
        previous_payload = {
            "topology": {
                "authoritative_links": [],
                "inferred_links": [
                    {
                        "source_port_id": "sw1:1",
                        "target_port_id": "sw2:2",
                        "source_device": "sw1",
                        "target_device": "sw2",
                        "source_inst_name": "sw1-port1",
                        "target_inst_name": "sw2-port2",
                        "relationship_type": "inferred",
                        "evidence_source": "arp",
                        "confidence": 50,
                    }
                ],
            }
        }

        previous_links = extract_previous_links(previous_payload)
        parsed = parse_aggregate_result(current, previous_links=previous_links)

        self.assertEqual(parsed["summary"]["stale_links"], 1)
        self.assertEqual(parsed["topology"]["stale_links"][0]["status"], "stale")

    def test_unresolved_neighbor_is_preserved_in_output(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [],
                                "ip": [],
                                "arp": [],
                                "neighbors": [{"tag": "LLDP-RemSysName", "ifindex": "0.99.1", "val": "sw2"}],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                }
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["unresolved_neighbors"], 1)
        self.assertEqual(result["topology"]["unresolved_neighbors"][0]["resolution_state"], "unresolved_local_port")

    def test_cdp_without_remote_port_does_not_get_extra_identifier_confidence(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [{"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"}],
                                "ip": [],
                                "arp": [],
                                "neighbors": [
                                    {"tag": "CDP-DeviceId", "ifindex": "1.1", "val": "sw2"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                }
            ]
        }

        result = parse_aggregate_result(aggregate)
        self.assertEqual(result["summary"]["unresolved_neighbors"], 1)
        self.assertEqual(result["topology"]["unresolved_neighbors"][0]["confidence"], 40)

    def test_unresolved_neighbor_on_linked_source_port_gets_conflict_reference(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xaaaaaaaaaaaa"},
                                ],
                                "ip": [],
                                "arp": [{"tag": "ARP-IfIndex", "ifindex": "10.0.0.2", "val": "1"}, {"tag": "ARP-PhysAddress", "ifindex": "10.0.0.2", "val": "0xbbbbbbbbbbbb"}],
                                "neighbors": [{"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "sw3"}],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "2", "val": "Eth2"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        unresolved = result["topology"]["unresolved_neighbors"][0]
        self.assertIsNotNone(unresolved["conflicts_with_relationship_id"])
        self.assertTrue(unresolved["conflicting_signals"])

    def test_conflict_reference_prefers_authoritative_link_over_inferred_link(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "sw1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xaaaaaaaaaaaa"},
                                ],
                                "ip": [],
                                "arp": [{"tag": "ARP-IfIndex", "ifindex": "10.0.0.2", "val": "1"}, {"tag": "ARP-PhysAddress", "ifindex": "10.0.0.2", "val": "0xbbbbbbbbbbbb"}],
                                "neighbors": [
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "sw3"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.1", "val": "Eth9"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.1", "val": "5"},
                                    {"tag": "LLDP-RemSysName", "ifindex": "0.1.2", "val": "sw4"},
                                    {"tag": "LLDP-RemPortId", "ifindex": "0.1.2", "val": "UnknownPort"},
                                    {"tag": "LLDP-RemPortIdSubtype", "ifindex": "0.1.2", "val": "5"},
                                ],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw2"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "2", "val": "Eth2"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw3"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw3"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "9", "val": "Eth9"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "sw4"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw4"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "4", "val": "Eth4"},
                                ],
                                "ip": [],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        authoritative_id = result["topology"]["authoritative_links"][0]["relationship_id"]
        unresolved = result["topology"]["unresolved_neighbors"][0]
        self.assertEqual(unresolved["conflicts_with_relationship_id"], authoritative_id)

    def test_same_device_alias_does_not_false_positive_as_conflict(self) -> None:
        aggregate = {
            "devices": [
                {
                    "device": {"host": "10.0.0.1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "sw1"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "1", "val": "Eth1"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xaaaaaaaaaaaa"},
                                ],
                                "ip": [],
                                "arp": [{"tag": "ARP-IfIndex", "ifindex": "10.0.0.2", "val": "1"}, {"tag": "ARP-PhysAddress", "ifindex": "10.0.0.2", "val": "0xbbbbbbbbbbbb"}],
                                "neighbors": [{"tag": "LLDP-RemSysName", "ifindex": "0.1.1", "val": "switch-2"}],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "10.0.0.2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [{"tag": "System-SysName", "ifindex": "", "val": "switch-2"}],
                                "interfaces": [
                                    {"tag": "IFXTable-IfName", "ifindex": "2", "val": "Eth2"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "2", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [{"tag": "IpAddr-IpAddr", "ifindex": "10.0.0.2", "val": "10.0.0.2"}],
                                "arp": [],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        unresolved = result["topology"]["unresolved_neighbors"][0]
        self.assertIsNone(unresolved["conflicts_with_relationship_id"])
        self.assertEqual(unresolved["conflicting_signals"], [])

    def test_cdp_local_index_resolves_as_ifindex_not_bridge_port(self) -> None:
        # bridge basePort "5" -> ifIndex "23"，与 ifIndex "5" 编号重叠。
        # CDP 索引第一段就是 ifIndex，必须解析到 dev:5 而不是 dev:23。
        ports = {
            "dev:5": NormalizedPort(device_id="dev", port_id="dev:5", ifindex="5", ifname="GigabitEthernet0/0/5"),
            "dev:23": NormalizedPort(device_id="dev", port_id="dev:23", ifindex="23", ifname="GigabitEthernet0/0/23"),
        }
        port_id, state = resolve_local_neighbor_port_id(
            device_id="dev",
            local_port_num="5",
            lldp_local_fields={},
            bridge_port_map={"dev": {"5": "23"}},
            ports=ports,
            protocol="cdp",
        )
        self.assertEqual(port_id, "dev:5")
        self.assertEqual(state, "resolved")

    def test_fdp_local_index_resolves_as_ifindex_not_bridge_port(self) -> None:
        ports = {
            "dev:5": NormalizedPort(device_id="dev", port_id="dev:5", ifindex="5", ifname="ethernet1/5"),
            "dev:23": NormalizedPort(device_id="dev", port_id="dev:23", ifindex="23", ifname="ethernet1/23"),
        }
        port_id, state = resolve_local_neighbor_port_id(
            device_id="dev",
            local_port_num="5",
            lldp_local_fields={},
            bridge_port_map={"dev": {"5": "23"}},
            ports=ports,
            protocol="fdp",
        )
        self.assertEqual(port_id, "dev:5")
        self.assertEqual(state, "resolved")

    def test_lldp_bridge_hit_rejected_by_local_name_mismatch(self) -> None:
        # bridge basePort "5" -> ifIndex "23"，但 LLDP-LocPortId 名称指向 ifIndex "5" 的端口，
        # 名称交叉校验应否决 bridge 候选并降级到名称匹配。
        ports = {
            "dev:5": NormalizedPort(device_id="dev", port_id="dev:5", ifindex="5", ifname="GigabitEthernet0/0/5"),
            "dev:23": NormalizedPort(device_id="dev", port_id="dev:23", ifindex="23", ifname="GigabitEthernet0/0/23"),
        }
        port_id, state = resolve_local_neighbor_port_id(
            device_id="dev",
            local_port_num="5",
            lldp_local_fields={"LLDP-LocPortId": "GigabitEthernet0/0/5", "LLDP-LocPortIdSubtype": "5"},
            bridge_port_map={"dev": {"5": "23"}},
            ports=ports,
            protocol="lldp",
        )
        self.assertEqual(port_id, "dev:5")
        self.assertEqual(state, "resolved")

    def test_lldp_bridge_hit_kept_when_no_name_evidence(self) -> None:
        # 无名称证据时维持 bridge 优先的旧行为。
        ports = {
            "dev:5": NormalizedPort(device_id="dev", port_id="dev:5", ifindex="5", ifname="GigabitEthernet0/0/5"),
            "dev:23": NormalizedPort(device_id="dev", port_id="dev:23", ifindex="23", ifname="GigabitEthernet0/0/23"),
        }
        port_id, state = resolve_local_neighbor_port_id(
            device_id="dev",
            local_port_num="5",
            lldp_local_fields={},
            bridge_port_map={"dev": {"5": "23"}},
            ports=ports,
            protocol="lldp",
        )
        self.assertEqual(port_id, "dev:23")
        self.assertEqual(state, "resolved")


    def test_reverse_direction_duplicate_becomes_supporting_evidence(self) -> None:
        # 两台设备互指的 ARP 记录：正向 ARP 产生 inferred_link，反向 ARP 应成为 supporting_evidence
        aggregate = {
            "devices": [
                {
                    "device": {"host": "10.0.0.1"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [
                                    {"tag": "IFTable-IfDescr", "ifindex": "1", "val": "ge-0/0/1"},
                                    {"tag": "IFTable-IfAlias", "ifindex": "1", "val": "uplink-a"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "1", "val": "0xaaaaaaaaaaaa"},
                                ],
                                "ip": [],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.0.0.2", "val": "1"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.0.0.2", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
                {
                    "device": {"host": "10.0.0.2"},
                    "success": True,
                    "collector_result": {
                        "result": {
                            "evidence": {
                                "system": [],
                                "interfaces": [
                                    {"tag": "IFTable-IfDescr", "ifindex": "5", "val": "ge-0/0/5"},
                                    {"tag": "IFTable-IfAlias", "ifindex": "5", "val": "uplink-b"},
                                    {"tag": "IFTable-PhysAddress", "ifindex": "5", "val": "0xbbbbbbbbbbbb"},
                                ],
                                "ip": [],
                                "arp": [
                                    {"tag": "ARP-IfIndex", "ifindex": "10.0.0.1", "val": "5"},
                                    {"tag": "ARP-PhysAddress", "ifindex": "10.0.0.1", "val": "0xaaaaaaaaaaaa"},
                                ],
                                "neighbors": [],
                                "bridge": [],
                                "fdb": [],
                            }
                        }
                    },
                },
            ]
        }

        result = parse_aggregate_result(aggregate)
        inferred_link = result["topology"]["inferred_links"][0]
        supporting = inferred_link["supporting_evidence"]
        self.assertEqual(len(supporting), 1)
        self.assertEqual(supporting[0]["disposition"], "corroborating")
        self.assertEqual(supporting[0]["winner_link_id"], inferred_link["relationship_id"])


if __name__ == "__main__":
    unittest.main()
