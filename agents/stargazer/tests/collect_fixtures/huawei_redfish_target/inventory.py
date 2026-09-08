"""华为 iBMC 风格的合成清单；不是固件抓包或机型兼容认证。"""

PROFILES = ("x86", "arm")
SCENARIOS = ("healthy", "partial", "unauthorized", "multi-system", "paginated", "unavailable")


def link(path):
    return {"@odata.id": path}


def build_inventory(profile="x86", scenario="healthy"):
    if profile not in PROFILES or scenario not in SCENARIOS:
        raise ValueError("unknown mock profile or scenario")
    resources = {}

    def resource(path, kind, **fields):
        resources[path] = {"@odata.id": path, "@odata.type": kind, "Id": path.rsplit("/", 1)[-1], **fields}
        return resources[path]

    def collection(path, kind, members):
        resources[path] = {
            "@odata.id": path,
            "@odata.type": f"#{kind}Collection.{kind}Collection",
            "Name": f"{kind} Collection",
            "Members@odata.count": len(members),
            "Members": [link(member) for member in members],
        }

    root = "/redfish/v1"
    resource(
        root,
        "#ServiceRoot.v1_5_0.ServiceRoot",
        Name="Synthetic iBMC target",
        RedfishVersion="1.6.0",
        Systems=link(f"{root}/Systems"),
        Chassis=link(f"{root}/Chassis"),
        Managers=link(f"{root}/Managers"),
        SessionService=link(f"{root}/SessionService"),
        Links={"Sessions": link(f"{root}/SessionService/Sessions")},
    )
    resource(f"{root}/SessionService", "#SessionService.v1_0_0.SessionService", Sessions=link(f"{root}/SessionService/Sessions"))
    ids = ["1", "Blade2"] if scenario == "multi-system" else ["1"]
    collection(f"{root}/Systems", "ComputerSystem", [f"{root}/Systems/{sid}" for sid in ids])
    collection(f"{root}/Chassis", "Chassis", [f"{root}/Chassis/{sid}" for sid in ids])
    collection(f"{root}/Managers", "Manager", [f"{root}/Managers/{sid}" for sid in ids])
    arm = profile == "arm"
    for number, sid in enumerate(ids, 1):
        system = f"{root}/Systems/{sid}"
        chassis = f"{root}/Chassis/{sid}"
        manager = f"{root}/Managers/{sid}"
        status = {"State": "Enabled", "Health": "OK"}
        resource(
            system,
            "#ComputerSystem.v1_6_0.ComputerSystem",
            Name=f"Synthetic server {sid}",
            SystemType="Physical",
            Manufacturer="Huawei",
            Model="TaiShan 200 (synthetic)" if arm else "2288H V5 (synthetic)",
            SerialNumber=f"MOCK-{profile.upper()}-SERVER-{number:03d}",
            UUID=f"00000000-0000-4000-8000-{number:012d}",
            BiosVersion="MOCK-BIOS-1.0",
            PowerState="On",
            Status=status,
            ProcessorSummary={"Count": 2, "Model": "Kunpeng (synthetic)" if arm else "Xeon (synthetic)"},
            MemorySummary={"TotalSystemMemoryGiB": 256},
            Processors=link(f"{system}/Processors"),
            Memory=link(f"{system}/Memory"),
            Storage=link(f"{system}/Storage"),
            EthernetInterfaces=link(f"{system}/EthernetInterfaces"),
            Links={"Chassis": [link(chassis)], "ManagedBy": [link(manager)]},
        )
        resource(
            chassis,
            "#Chassis.v1_7_0.Chassis",
            Name="Synthetic chassis",
            ChassisType="RackMount",
            Links={"ComputerSystems": [link(system)], "ManagedBy": [link(manager)]},
        )
        resource(
            manager,
            "#Manager.v1_3_0.Manager",
            Name="iBMC (synthetic)",
            ManagerType="BMC",
            FirmwareVersion="MOCK-iBMC-1.0",
            EthernetInterfaces=link(f"{manager}/EthernetInterfaces"),
            Links={"ManagerForServers": [link(system)], "ManagerForChassis": [link(chassis)]},
        )
        for suffix, kind, count in [("Processors", "Processor", 2), ("Memory", "Memory", 8), ("EthernetInterfaces", "EthernetInterface", 2)]:
            collection(f"{system}/{suffix}", kind, [f"{system}/{suffix}/{i}" for i in range(1, count + 1)])
        for i in range(1, 3):
            resource(
                f"{system}/Processors/{i}",
                "#Processor.v1_0_0.Processor",
                Name=f"CPU{i}",
                ProcessorType="CPU",
                Manufacturer="Huawei" if arm else "Intel",
                Model="Synthetic ARM CPU" if arm else "Synthetic x86 CPU",
                ProcessorArchitecture="ARM" if arm else "x86",
                InstructionSet="ARM-A64" if arm else "x86-64",
                TotalCores=64 if arm else 20,
                TotalThreads=64 if arm else 40,
                MaxSpeedMHz=2600,
                Socket=str(i),
                Status=status,
            )
            resource(
                f"{system}/EthernetInterfaces/{i}",
                "#EthernetInterface.v1_0_0.EthernetInterface",
                Name=f"NIC{i}",
                MACAddress=f"02:00:00:{number:02x}:00:{i:02x}",
                SpeedMbps=10000,
                Status=status,
            )
        for i in range(1, 9):
            resource(
                f"{system}/Memory/{i}",
                "#Memory.v1_0_0.Memory",
                Name=f"DIMM{i}",
                CapacityMiB=32768,
                DeviceLocator=f"DIMM{i:03d}",
                MemoryDeviceType="DDR4",
                OperatingSpeedMhz=2666,
                SerialNumber=f"MOCK-{number}-DIMM-{i}",
                PartNumber="MOCK-DDR4-32G",
                Manufacturer="Synthetic",
                Status=status,
            )
        # 管理口与主机网卡使用不同资源及 MAC，防止采集器把管理口当业务网卡。
        collection(f"{manager}/EthernetInterfaces", "EthernetInterface", [f"{manager}/EthernetInterfaces/1"])
        resource(
            f"{manager}/EthernetInterfaces/1",
            "#EthernetInterface.v1_0_0.EthernetInterface",
            Name="Management port",
            MACAddress=f"02:00:00:{number:02x}:ff:01",
            SpeedMbps=1000,
        )
        storage = f"{system}/Storage/RAID1"
        drives = [f"{chassis}/Drives/{i}" for i in range(1, 3)]
        collection(f"{system}/Storage", "Storage", [storage])
        collection(f"{chassis}/Drives", "Drive", drives)
        resource(
            storage, "#Storage.v1_3_0.Storage", Name="Synthetic RAID controller", Drives=[link(p) for p in drives], Volumes=link(f"{storage}/Volumes")
        )
        for i, path in enumerate(drives, 1):
            resource(
                path,
                "#Drive.v1_0_0.Drive",
                Name=f"Disk{i}",
                CapacityBytes=960_000_000_000 * number,
                Protocol="SAS",
                MediaType="SSD",
                SerialNumber=f"MOCK-{number}-DISK-{i}",
                Manufacturer="Synthetic",
                Model="MOCK-SSD",
                Status=status,
            )
        collection(f"{storage}/Volumes", "Volume", [f"{storage}/Volumes/1"])
        resource(
            f"{storage}/Volumes/1",
            "#Volume.v1_4_0.Volume",
            Name="Logical disk 1",
            RAIDType="RAID1",
            VolumeType="Mirrored",
            CapacityBytes=960_000_000_000 * number,
            Links={"Drives": [link(p) for p in drives]},
            Status=status,
        )
    if scenario == "paginated":
        path = f"{root}/Systems/1/Memory"
        members = resources[path]["Members"]
        resources[path]["Members"] = members[:4]
        resources[path]["Members@odata.nextLink"] = f"{path}?page=2"
        resources[f"{path}?page=2"] = {**resources[path], "Members": members[4:]}
        del resources[f"{path}?page=2"]["Members@odata.nextLink"]
    return resources
