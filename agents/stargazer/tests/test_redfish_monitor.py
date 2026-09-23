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


def test_monitor_factory_loads_redfish_collector():
    assert _load_monitor_collector("redfish") is RedfishCollector
