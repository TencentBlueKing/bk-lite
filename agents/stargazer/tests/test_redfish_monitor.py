import pytest
from core.collection.plugins import _load_monitor_collector
from tasks.collectors.redfish_collector import FORBIDDEN_URI_PARTS, RedfishCollector, RedfishMonitorError, is_inlet_sensor


def _collector() -> RedfishCollector:
    return RedfishCollector({"host": "10.2.13.51", "username": "ro", "password": "secret"})


def _values(current: dict, name: str):
    raw = current.get(name)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [point[1] for point in raw]
    return [points[0][1] for points in raw.values()]


def _named(current: dict, name: str) -> dict[str, float]:
    raw = current.get(name) or {}
    out = {}
    for dims, points in raw.items():
        labels = dict(dims)
        out[labels.get("name") or labels.get("id")] = points[0][1]
    return out


def test_emit_inlet_temperature_from_thermal_inlet_sensor():
    current = {}
    _collector()._emit_thermal_metrics(
        current,
        {
            "Temperatures": [
                {"Name": "CPU1 Temp", "ReadingCelsius": 52, "UpperThresholdCritical": 98},
                {
                    "Name": "System Board Inlet Temp",
                    "ReadingCelsius": 22,
                    "UpperThresholdCritical": 47,
                    "PhysicalContext": "SystemBoard",
                },
                {"Name": "System Board Exhaust Temp", "ReadingCelsius": 33, "UpperThresholdCritical": 80},
            ]
        },
    )

    assert _values(current, "redfish_inlet_temperature_celsius") == [22]
    assert _values(current, "redfish_inlet_temperature_upper_critical_celsius") == [47]
    assert _named(current, "redfish_temperature_celsius")["System Board Inlet Temp"] == 22


def test_hotter_inlet_without_threshold_does_not_keep_cooler_upper():
    current = {}
    _collector()._emit_thermal_metrics(
        current,
        {
            "Temperatures": [
                {
                    "Name": "Front Inlet",
                    "ReadingCelsius": 18,
                    "UpperThresholdCritical": 40,
                    "PhysicalContext": "Intake",
                },
                {
                    "Name": "Rear Inlet",
                    "ReadingCelsius": 26,
                    "PhysicalContext": "Intake",
                },
            ]
        },
    )

    assert _values(current, "redfish_inlet_temperature_celsius") == [26]
    assert current.get("redfish_inlet_temperature_upper_critical_celsius") is None


def test_emit_power_redundancy_and_limit_from_idrac_sample():
    current = {}
    _collector()._emit_power_metrics(
        current,
        {
            "PowerControl": [
                {
                    "Name": "System Power Control",
                    "PowerConsumedWatts": 417,
                    "PowerLimit": {"LimitInWatts": 320},
                }
            ],
            "PowerSupplies": [
                {
                    "Name": "PS1 Status",
                    "PowerCapacityWatts": 1600,
                    "PowerInputWatts": 380.5,
                    "PowerOutputWatts": 364.5,
                    "Status": {"Health": "OK"},
                },
                {
                    "Name": "PS2 Status",
                    "PowerCapacityWatts": 1600,
                    "PowerInputWatts": 5,
                    "PowerOutputWatts": 0,
                    "Status": {"Health": "OK"},
                },
            ],
        },
    )

    outputs = _named(current, "redfish_psu_output_watts")
    assert outputs["PS1 Status"] == 364.5
    assert outputs["PS2 Status"] == 0
    assert _named(current, "redfish_psu_capacity_watts")["PS1 Status"] == 1600
    assert _named(current, "redfish_psu_delivering") == {"PS1 Status": 1, "PS2 Status": 0}
    assert _values(current, "redfish_psu_redundant") == [0]
    assert _values(current, "redfish_power_limit_watts") == [320]
    assert _values(current, "redfish_power_over_limit") == [1]


def test_emit_drive_health_count_and_life():
    current = {}
    _collector()._emit_drive_metrics(
        current,
        [
            {
                "Name": "Physical Disk 0:1:5",
                "Id": "Disk.Bay.5:Enclosure.Internal.0-1:NonRAID.Slot.6-1",
                "MediaType": "HDD",
                "Protocol": "SAS",
                "Status": {"Health": "OK", "State": "Enabled"},
            },
            {
                "Name": "SSD 0",
                "Id": "Disk.Direct.0-0:AHCI.Slot.3-1",
                "MediaType": "SSD",
                "Protocol": "SATA",
                "PredictedMediaLifeLeftPercent": 86,
                "Status": {"Health": "Warning", "State": "Enabled"},
            },
            {
                "Name": "Empty Bay",
                "Id": "Disk.Bay.4",
                "Status": {"State": "Absent"},
            },
        ],
    )

    health = _named(current, "redfish_drive_health")
    assert health["Physical Disk 0:1:5"] == 1
    assert health["SSD 0"] == 2
    assert "Empty Bay" not in health
    assert _values(current, "redfish_drive_present_count") == [2]
    assert _named(current, "redfish_drive_life_percent")["SSD 0"] == 86


def test_inlet_matcher_accepts_intake_physical_context():
    assert is_inlet_sensor({"PhysicalContext": "Intake"}, "Temp 1")
    assert not is_inlet_sensor({"PhysicalContext": "CPU"}, "CPU1 Temp")


def test_resource_url_allows_storage_drives_and_still_blocks_sensors():
    collector = _collector()
    url = collector._resource_url("/redfish/v1/Systems/1/Storage/RAID/Drives/Disk.Bay.5")
    assert url.endswith("/Storage/RAID/Drives/Disk.Bay.5")
    assert "/drives" not in FORBIDDEN_URI_PARTS
    with pytest.raises(RedfishMonitorError, match="not allowed"):
        collector._resource_url("/redfish/v1/Chassis/1/Sensors")


@pytest.mark.asyncio
async def test_list_drives_follows_storage_drive_links_and_skips_missing():
    collector = _collector()
    requested = []

    async def fake_get(_client, link, optional=False):
        requested.append((link, optional))
        if link.endswith("/missing"):
            return None
        return {"Id": "d1", "Name": "Disk 1", "Status": {"Health": "OK", "State": "Enabled"}}

    collector._get_json = fake_get
    drives = await collector._list_drives(
        object(),
        [
            {
                "Drives": [
                    {"@odata.id": "/redfish/v1/Systems/1/Storage/RAID/Drives/0"},
                    {"@odata.id": "/redfish/v1/Systems/1/Storage/RAID/Drives/missing"},
                ]
            }
        ],
    )

    assert requested == [
        ("/redfish/v1/Systems/1/Storage/RAID/Drives/0", True),
        ("/redfish/v1/Systems/1/Storage/RAID/Drives/missing", True),
    ]
    assert [drive["Name"] for drive in drives] == ["Disk 1"]


@pytest.mark.asyncio
async def test_resolve_drives_keeps_storage_path_and_skips_chassis_fallback():
    """When Storage.Drives already returned disks, do not GET Chassis/Drives."""
    collector = _collector()
    requested = []

    async def fake_get(_client, link, optional=False, **_kwargs):
        requested.append(link)
        return {"Id": "d1", "Name": "RAID Disk", "Status": {"Health": "OK", "State": "Enabled"}}

    collector._get_json = fake_get
    drives = await collector._resolve_drives(
        object(),
        [{"Drives": [{"@odata.id": "/redfish/v1/Systems/1/Storage/RAID/Drives/0"}]}],
        [{"@odata.id": "/redfish/v1/Chassis/1", "Drives": {"@odata.id": "/redfish/v1/Chassis/1/Drives"}}],
    )

    assert [drive["Name"] for drive in drives] == ["RAID Disk"]
    assert requested == ["/redfish/v1/Systems/1/Storage/RAID/Drives/0"]
    assert not any("/Chassis/1/Drives" in link for link in requested)


@pytest.mark.asyncio
async def test_resolve_drives_falls_back_to_chassis_drives_when_storage_empty():
    """Inspur-style Chassis/Drives is used only after Storage.Drives is empty."""
    collector = _collector()

    async def fake_get(_client, link, optional=False, **_kwargs):
        if str(link).rstrip("/").endswith("/Chassis/1/Drives"):
            return {
                "Members": [
                    {"@odata.id": "/redfish/v1/Chassis/1/Drives/HDDPlaneDisk0"},
                    {"@odata.id": "/redfish/v1/Chassis/1/Drives/HDDPlaneDisk1"},
                ]
            }
        if str(link).endswith("HDDPlaneDisk0"):
            return {
                "Id": "HDDPlaneDisk0",
                "Name": "Disk0",
                "MediaType": "SSD",
                "Status": {"Health": "OK", "State": "Enabled"},
            }
        if str(link).endswith("HDDPlaneDisk1"):
            return {
                "Id": "HDDPlaneDisk1",
                "Name": "Disk1",
                "MediaType": "SSD",
                "Status": {"Health": "OK", "State": "Enabled"},
            }
        return None

    collector._get_json = fake_get
    drives = await collector._resolve_drives(
        object(),
        [],
        [{"@odata.id": "/redfish/v1/Chassis/1"}],
    )

    assert [drive["Name"] for drive in drives] == ["Disk0", "Disk1"]


@pytest.mark.asyncio
async def test_resolve_nics_keeps_network_adapters_and_skips_ethernet_fallback():
    collector = _collector()
    requested = []

    async def fake_get(_client, link, optional=False, **_kwargs):
        requested.append(str(link))
        text = str(link)
        if text.endswith("/NetworkAdapters"):
            return {"Members": [{"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/ob-1"}]}
        if text.endswith("/ob-1"):
            return {
                "Id": "ob-1",
                "Name": "Onboard NIC",
                "Status": {"Health": "OK"},
                "NetworkPorts": {"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/ob-1/NetworkPorts"},
            }
        if text.endswith("/NetworkPorts"):
            return {"Members": [{"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/ob-1/NetworkPorts/1"}]}
        if text.endswith("/NetworkPorts/1"):
            return {"Id": "1", "Name": "Port 1", "LinkStatus": "LinkUp", "Status": {"Health": "OK"}}
        raise AssertionError(f"unexpected GET {link}")

    collector._get_json = fake_get
    rows = await collector._resolve_nics(
        object(),
        "/redfish/v1/Chassis/1/NetworkAdapters",
        {"EthernetInterfaces": {"@odata.id": "/redfish/v1/Systems/1/EthernetInterfaces"}},
    )

    assert len(rows) == 1
    adapter, ports = rows[0]
    assert adapter["Id"] == "ob-1"
    assert ports[0]["Id"] == "1"
    assert not any("EthernetInterfaces" in link for link in requested)


@pytest.mark.asyncio
async def test_resolve_nics_falls_back_to_ethernet_interfaces_when_adapters_empty():
    collector = _collector()

    async def fake_get(_client, link, optional=False, **_kwargs):
        text = str(link)
        if text.endswith("/EthernetInterfaces"):
            return {"Members": [{"@odata.id": "/redfish/v1/Systems/1/EthernetInterfaces/eth0"}]}
        if text.endswith("/eth0"):
            return {
                "Id": "eth0",
                "Name": "NIC1",
                "LinkStatus": "LinkUp",
                "SpeedMbps": 1000,
                "Status": {"Health": "OK", "State": "Enabled"},
            }
        return None

    collector._get_json = fake_get
    rows = await collector._resolve_nics(
        object(),
        "",
        {"EthernetInterfaces": {"@odata.id": "/redfish/v1/Systems/1/EthernetInterfaces"}},
    )

    assert len(rows) == 1
    adapter, ports = rows[0]
    current = {}
    collector._emit_nic_metrics(current, rows)
    assert adapter["Id"] == "eth0"
    assert ports[0]["SpeedMbps"] == 1000
    assert _named(current, "redfish_nic_health")["eth0"] == 1
    assert _values(current, "redfish_nic_port_link_up") == [1]
    assert _values(current, "redfish_nic_port_speed_mbps") == [1000]


def test_ethernetinterfaces_remain_forbidden_on_generic_resource_url():
    collector = _collector()
    with pytest.raises(RedfishMonitorError, match="not allowed"):
        collector._resource_url("/redfish/v1/Systems/1/EthernetInterfaces")


def test_port_speed_uses_speed_mbps_only_when_standard_fields_missing():
    from tasks.collectors.redfish_collector import port_speed_mbps

    assert port_speed_mbps({"CurrentLinkSpeedMbps": 25000, "SpeedMbps": 1000}) == 25000
    assert port_speed_mbps({"CurrentSpeedGbps": 10, "SpeedMbps": 1000}) == 10000
    assert port_speed_mbps({"SpeedMbps": 1000}) == 1000


def test_health_code_uses_rollup_only_when_health_empty():
    from tasks.collectors.redfish_collector import health_code

    assert health_code({"Health": "Warning", "HealthRollup": "OK"}) == 2
    assert health_code({"Health": "", "HealthRollup": "OK"}) == 1
    assert health_code({"HealthRollup": "OK"}) == 1


def test_health_code_maps_ok_with_trailing_punctuation():
    from tasks.collectors.redfish_collector import health_code

    assert health_code({"Health": "OK"}) == 1
    assert health_code({"Health": "OK!"}) == 1
    assert health_code({"Health": "Critical"}) == 3


def test_processor_memory_rollup_emits_when_only_healthrollup_present():
    current = {}
    _collector()._emit_system_metrics(
        current,
        {
            "Id": "1",
            "PowerState": "On",
            "Status": {"Health": "OK"},
            "ProcessorSummary": {"Status": {"Health": None, "HealthRollup": "OK"}},
            "MemorySummary": {"Status": {"Health": "", "HealthRollup": "OK"}},
        },
        {"FirmwareVersion": "1.0", "Status": {"Health": "OK!"}},
    )
    assert _values(current, "redfish_processor_health_rollup") == [1]
    assert _values(current, "redfish_memory_health_rollup") == [1]
    assert _values(current, "redfish_manager_health") == [1]


def test_psu_delivering_uses_output_watts_when_input_missing():
    current = {}
    _collector()._emit_power_metrics(
        current,
        {
            "PowerSupplies": [
                {
                    "Name": "PSU0",
                    "PowerCapacityWatts": 1200,
                    "PowerOutputWatts": 192.75,
                    "Status": {"Health": "OK"},
                },
                {
                    "Name": "PSU1",
                    "PowerCapacityWatts": 1200,
                    "PowerOutputWatts": 178.0,
                    "Status": {"Health": "OK"},
                },
            ]
        },
    )
    assert _named(current, "redfish_psu_delivering") == {"PSU0": 1, "PSU1": 1}
    assert _values(current, "redfish_psu_redundant") == [1]


def test_psu_delivering_keeps_input_watts_when_present():
    current = {}
    _collector()._emit_power_metrics(
        current,
        {
            "PowerSupplies": [
                {
                    "Name": "PSU0",
                    "PowerInputWatts": 5,
                    "PowerOutputWatts": 180,
                    "Status": {"Health": "OK"},
                }
            ]
        },
    )
    assert _named(current, "redfish_psu_delivering") == {"PSU0": 0}


@pytest.mark.asyncio
async def test_resolve_nics_falls_back_when_adapters_have_no_health_or_ports():
    collector = _collector()
    requested = []

    async def fake_get(_client, link, optional=False, **_kwargs):
        requested.append(str(link))
        text = str(link)
        if text.endswith("/NetworkAdapters"):
            return {"Members": [{"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/card2"}]}
        if text.endswith("/card2"):
            return {"Id": "mainboardPCIeCard2", "Name": "PCIeCard2", "Status": {"Health": ""}}
        if text.endswith("/EthernetInterfaces"):
            return {"Members": [{"@odata.id": "/redfish/v1/Systems/1/EthernetInterfaces/eth0"}]}
        if text.endswith("/eth0"):
            return {
                "Id": "eth0",
                "Name": "NIC1",
                "LinkStatus": "LinkUp",
                "SpeedMbps": 1000,
                "Status": {"Health": "OK"},
            }
        return None

    collector._get_json = fake_get
    rows = await collector._resolve_nics(
        object(),
        "/redfish/v1/Chassis/1/NetworkAdapters",
        {"EthernetInterfaces": {"@odata.id": "/redfish/v1/Systems/1/EthernetInterfaces"}},
    )
    current = {}
    collector._emit_nic_metrics(current, rows)
    assert any("EthernetInterfaces" in link for link in requested)
    assert _named(current, "redfish_nic_health")["eth0"] == 1
    assert _values(current, "redfish_nic_port_link_up") == [1]


def test_tls_context_keeps_verify_flag_and_offers_rsa_gcm():
    import ssl

    from tasks.collectors.redfish_collector import _tls_verify

    ctx = _tls_verify(True)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    assert "AES256-GCM-SHA384" in {item["name"] for item in ctx.get_ciphers()}

    ctx = _tls_verify(False)
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False
    assert "AES256-GCM-SHA384" in {item["name"] for item in ctx.get_ciphers()}


def test_monitor_client_uses_tls_context(monkeypatch):
    import ssl

    import httpx

    captured = {}
    real_async_client = httpx.AsyncClient

    def client_factory(**kwargs):
        captured["verify"] = kwargs["verify"]
        return real_async_client(**kwargs)

    monkeypatch.setattr("tasks.collectors.redfish_collector.httpx.AsyncClient", client_factory)
    _collector()._client()
    ctx = captured["verify"]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert "AES256-GCM-SHA384" in {item["name"] for item in ctx.get_ciphers()}


def test_monitor_factory_loads_redfish_collector():
    assert _load_monitor_collector("redfish") is RedfishCollector
