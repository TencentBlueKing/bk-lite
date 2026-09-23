from plugins.inputs.physcial_server.redfish_inventory import build_redfish_result


def test_build_redfish_result_maps_standard_inventory():
    result = build_redfish_result(
        {"ip_addr": "10.0.0.8", "port": 443, "serial_number": "SERVER-SN-8"},
        processors=[
            {
                "Manufacturer": "Intel",
                "Model": "Xeon Gold",
                "TotalCores": 16,
                "TotalThreads": 32,
                "InstructionSet": "x86-64",
            },
            {"ProcessorType": "CPU", "TotalCores": 16, "TotalThreads": 32},
            {"ProcessorType": "GPU", "Name": "A100", "Model": "NVIDIA A100"},
        ],
        memory=[
            {
                "DeviceLocator": "DIMM_A1",
                "PartNumber": "M393",
                "MemoryDeviceType": "DDR4",
                "CapacityMiB": 32768,
                "SerialNumber": "MEM-1",
            },
            {"Status": {"State": "Absent"}, "DeviceLocator": "DIMM_A2"},
        ],
        drives=[
            {
                "Id": "Disk.Bay.0",
                "Manufacturer": "Samsung",
                "MediaType": "SSD",
                "CapacityBytes": 480 * 1024**3,
                "SerialNumber": "DISK-1",
                "Protocol": "SATA",
            }
        ],
        nic_records=[
            {
                "adapter": {"Manufacturer": "Broadcom", "Model": "BCM5720"},
                "function": {
                    "NetDevFuncType": "Ethernet",
                    "Ethernet": {"MACAddress": "AA-BB-CC-DD-EE-FF"},
                },
            },
            {
                "adapter": {"Manufacturer": "Broadcom"},
                "function": {"Ethernet": {"MACAddress": "00:00:00:00:00:00"}},
            },
        ],
        assemblies=[
            {
                "PhysicalContext": "Chassis",
                "SerialNumber": "CHASSIS-SN",
                "Vendor": "Huawei",
            },
            {
                "PhysicalContext": "SystemBoard",
                "Vendor": "Huawei",
                "Model": "BC11",
                "SerialNumber": "BOARD-SN",
            },
        ],
    )

    assert result["physcial_server"] == [
        {
            "ip_addr": "10.0.0.8",
            "port": 443,
            "serial_number": "SERVER-SN-8",
            "cpu_vendor": "Intel",
            "cpu_model": "Xeon Gold",
            "cpu_cores": 32,
            "cpu_threads": 64,
            "cpu_arch": "x86_64",
            "board_vendor": "Huawei",
            "board_model": "BC11",
            "board_serial": "BOARD-SN",
        }
    ]
    assert result["memory"] == [
        {
            "mem_locator": "DIMM_A1",
            "mem_part_number": "M393",
            "mem_type": "DDR4",
            "mem_size": 32,
            "mem_sn": "MEM-1",
            "self_device": "10.0.0.8",
        }
    ]
    assert result["disk"] == [
        {
            "disk_name": "Disk.Bay.0",
            "disk_vendor": "Samsung",
            "disk_type": "SSD",
            "disk": 480,
            "disk_sn": "DISK-1",
            "self_device": "10.0.0.8",
        }
    ]
    assert result["nic"] == [
        {
            "nic_mac": "aa:bb:cc:dd:ee:ff",
            "nic_vendor": "Broadcom",
            "nic_model": "BCM5720",
            "nic_type": "Ethernet",
            "self_device": "10.0.0.8",
        }
    ]
    assert result["gpu"] == [
        {
            "gpu_name": "A100",
            "gpu_type": "GPU",
            "gpu_desc": "NVIDIA A100",
            "self_device": "10.0.0.8",
        }
    ]


def test_failed_or_empty_child_collections_omit_model_keys():
    result = build_redfish_result(
        {"ip_addr": "10.0.0.8"},
        processors=None,
        memory=[],
        drives=None,
        nic_records=None,
        assemblies=[],
    )

    assert set(result) == {"physcial_server"}
    assert "cpu_vendor" not in result["physcial_server"][0]
    assert "board_serial" not in result["physcial_server"][0]


def test_unknown_instruction_set_omits_cpu_arch():
    result = build_redfish_result(
        {"ip_addr": "10.0.0.8"},
        processors=[{"Manufacturer": "Vendor", "InstructionSet": "OEM"}],
        memory=None,
        drives=None,
        nic_records=None,
        assemblies=None,
    )

    assert result["physcial_server"][0]["cpu_vendor"] == "Vendor"
    assert "cpu_arch" not in result["physcial_server"][0]


def test_sub_gigabyte_capacity_is_omitted():
    result = build_redfish_result(
        {"ip_addr": "10.0.0.8"},
        processors=None,
        memory=[{"DeviceLocator": "DIMM_A1", "CapacityMiB": 512}],
        drives=[{"Id": "Disk.Bay.0", "CapacityBytes": 1024}],
        nic_records=None,
        assemblies=None,
    )

    assert "mem_size" not in result["memory"][0]
    assert "disk" not in result["disk"][0]


def test_board_model_falls_back_to_name():
    result = build_redfish_result(
        {"ip_addr": "10.0.0.8"},
        processors=None,
        memory=None,
        drives=None,
        nic_records=None,
        assemblies=[
            {
                "PhysicalContext": "SystemBoard",
                "Vendor": "Huawei",
                "Name": "BC11-Name",
                "Model": "",
                "SerialNumber": "BOARD-SN",
            }
        ],
    )

    assert result["physcial_server"][0]["board_model"] == "BC11-Name"


def test_blank_ip_addr_omits_self_device():
    result = build_redfish_result(
        {"ip_addr": "   "},
        processors=None,
        memory=[{"DeviceLocator": "DIMM_A1"}],
        drives=[{"Id": "Disk.Bay.0"}],
        nic_records=[
            {
                "function": {
                    "Ethernet": {"MACAddress": "AA-BB-CC-DD-EE-FF"},
                }
            }
        ],
        assemblies=None,
    )

    assert "self_device" not in result["memory"][0]
    assert "self_device" not in result["disk"][0]
    assert "self_device" not in result["nic"][0]


def test_nic_mac_falls_back_when_ethernet_mac_invalid():
    result = build_redfish_result(
        {"ip_addr": "10.0.0.8"},
        processors=None,
        memory=None,
        drives=None,
        nic_records=[
            {
                "function": {
                    "Ethernet": {"MACAddress": "00:00:00:00:00:00"},
                    "MACAddress": "AA-BB-CC-DD-EE-FF",
                }
            }
        ],
        assemblies=None,
    )

    assert result["nic"][0]["nic_mac"] == "aa:bb:cc:dd:ee:ff"


def test_cpu_zero_counts_are_written_when_present():
    result = build_redfish_result(
        {"ip_addr": "10.0.0.8"},
        processors=[
            {"Manufacturer": "Intel", "TotalCores": 0, "TotalThreads": 0},
            {"ProcessorType": "CPU"},
        ],
        memory=None,
        drives=None,
        nic_records=None,
        assemblies=None,
    )

    assert result["physcial_server"][0]["cpu_cores"] == 0
    assert result["physcial_server"][0]["cpu_threads"] == 0


def test_cpu_counts_omitted_when_no_processor_has_integer():
    result = build_redfish_result(
        {"ip_addr": "10.0.0.8"},
        processors=[{"Manufacturer": "Intel", "TotalCores": "16", "TotalThreads": None}],
        memory=None,
        drives=None,
        nic_records=None,
        assemblies=None,
    )

    assert "cpu_cores" not in result["physcial_server"][0]
    assert "cpu_threads" not in result["physcial_server"][0]


def test_server_identity_strings_are_stored_stripped():
    result = build_redfish_result(
        {"ip_addr": " 10.0.0.8 ", "serial_number": " SN-8 "},
        processors=None,
        memory=[{"DeviceLocator": "DIMM_A1"}],
        drives=None,
        nic_records=None,
        assemblies=None,
    )

    assert result["physcial_server"][0]["ip_addr"] == "10.0.0.8"
    assert result["physcial_server"][0]["serial_number"] == "SN-8"
    assert result["memory"][0]["self_device"] == "10.0.0.8"


def test_accelerator_total_cores_excluded_from_cpu_and_emitted_as_gpu():
    result = build_redfish_result(
        {"ip_addr": "10.0.0.8"},
        processors=[
            {"Manufacturer": "Intel", "TotalCores": 16, "TotalThreads": 32},
            {
                "ProcessorType": "Accelerator",
                "Name": "H100",
                "Model": "NVIDIA H100",
                "TotalCores": 64,
                "TotalThreads": 128,
            },
        ],
        memory=None,
        drives=None,
        nic_records=None,
        assemblies=None,
    )

    assert result["physcial_server"][0]["cpu_cores"] == 16
    assert result["physcial_server"][0]["cpu_threads"] == 32
    assert result["gpu"] == [
        {
            "gpu_name": "H100",
            "gpu_type": "Accelerator",
            "gpu_desc": "NVIDIA H100",
            "self_device": "10.0.0.8",
        }
    ]


def test_non_dict_members_are_skipped_without_error():
    result = build_redfish_result(
        {"ip_addr": " 10.0.0.8 "},
        processors=[
            None,
            {"Manufacturer": "Intel", "TotalCores": 8, "TotalThreads": 16},
            "x",
            {"ProcessorType": "Accelerator", "Name": "Acc1", "TotalCores": 64},
        ],
        memory=[None, {"DeviceLocator": "DIMM_A1"}, "bad"],
        drives=[None, {"Id": "Disk.0"}, 123],
        nic_records=[
            None,
            {
                "adapter": "not-a-dict",
                "function": {
                    "NetDevFuncType": "Ethernet",
                    "Ethernet": "not-a-dict",
                    "MACAddress": "AA-BB-CC-DD-EE-01",
                },
            },
            "x",
        ],
        assemblies=[
            None,
            "x",
            {
                "PhysicalContext": "SystemBoard",
                "Vendor": "Huawei",
                "Model": "M1",
                "SerialNumber": "B1",
            },
        ],
    )

    assert result["physcial_server"][0]["ip_addr"] == "10.0.0.8"
    assert result["physcial_server"][0]["cpu_cores"] == 8
    assert result["physcial_server"][0]["cpu_threads"] == 16
    assert result["physcial_server"][0]["board_model"] == "M1"
    assert result["memory"] == [{"mem_locator": "DIMM_A1", "self_device": "10.0.0.8"}]
    assert result["disk"] == [{"disk_name": "Disk.0", "self_device": "10.0.0.8"}]
    assert result["nic"] == [{"nic_mac": "aa:bb:cc:dd:ee:01", "nic_type": "Ethernet", "self_device": "10.0.0.8"}]
    assert result["gpu"] == [{"gpu_name": "Acc1", "gpu_type": "Accelerator", "self_device": "10.0.0.8"}]
