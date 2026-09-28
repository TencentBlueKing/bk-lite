### Overview
Collects hardware inventory of a physical server and syncs it to CMDB in a standardized form. Collection is **read-only**. This plugin provides three collection methods; choose by environment:

1. **Physical Server SSH (JOB)**: collect full hardware asset information via host-side commands.
2. **[BETA] Physical Server IPMI (protocol)**: collect basic identity information via the BMC management port, for out-of-band asset supplementation.
3. **[BETA] Physical Server Redfish (protocol)**: collect basic identity information via the BMC's standard HTTPS API.

All three methods build `physcial_server.inst_name` from the collection target IP. The first task that successfully writes a given IP owns that instance; other tasks are constrained by `collect_task` filtering and instance-name uniqueness, and will not update or recreate that instance.

---

## Method 1: Physical Server SSH (JOB)

### Execution Mode
This method is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Prerequisites (SSH method)
1. **Network connectivity**: the SSH port from the access point to the target is reachable (default `22`, customizable).
2. **Collection account and permissions**: **root / sudo is required**. The script uses `dmidecode` to read serial/motherboard/memory slots, and `hdparm` / `smartctl` / `nvme` to read disk serial numbers, all of which require root.
3. **Target dependencies**: `dmidecode`, `lscpu`, `lsblk`, `lspci`, `smartctl` or `hdparm`, `nvme`; GPU information optionally depends on `nvidia-smi`.

### Credential Fields (SSH method)
- `username`: SSH login username; must have root / sudo privileges.
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data (SSH method)
**Physical server (physcial_server)**

| Key | Description |
| :--- | :--- |
| serial_number | Chassis serial number |
| cpu_vendor | CPU vendor |
| cpu_model | CPU model |
| cpu_cores | CPU physical core count |
| cpu_threads | CPU thread count |
| cpu_arch | CPU architecture |
| board_vendor | Motherboard vendor |
| board_model | Motherboard model |
| board_serial | Motherboard serial number |

**Related children (attached under the physical server by containment/association)**
- Memory `memory`: `mem_*` fields.
- Disk `disk`: `disk_*` fields.
- NIC `nic`: `nic_*` fields.
- GPU `gpu`: `gpu_*` fields.

---

## Method 2: Physical Server IPMI (protocol, BETA)

### Overview
Collects basic identity information of a physical server via the BMC management port, agentless, with the access point connecting directly to the BMC.

### Prerequisites (IPMI method)
1. **Network connectivity**: port `623` from the access point to the BMC is reachable.
2. **Account permissions**: an IPMI account with read permission is enough.

### Credential Fields (IPMI method)
- `host`: BMC management-port IP.
- `port`: IPMI port, default `623`.
- `username`: IPMI username.
- `password`: IPMI password. Encrypted at rest.
- `privilege`: IPMI privilege level.

### Collected Data (IPMI method)
| Key | Description |
| :--- | :--- |
| ip_addr | BMC management-port IP |
| serial_number | Chassis serial number |
| model | Product model |
| brand | Vendor |
| asset_code | Asset tag |
| board_vendor | Motherboard vendor |
| board_model | Motherboard model |
| board_serial | Motherboard serial number |

> Note: the IPMI method only supplements basic identity fields and does not create `memory` / `disk` / `nic` / `gpu` related instances. Fields such as `asset_code` and `board_serial` depend on vendor FRU implementation and may be empty.

---

## Method 3: Physical Server Redfish (protocol, BETA)

### Overview
Redfish is the standard REST API provided by a server BMC. This method reads `/redfish/v1/` and the unique `ComputerSystem` resource via HTTPS Basic Auth. It does not depend on the target OS and does not perform write operations.

### Prerequisites (Redfish method)
1. **Network connectivity**: the HTTPS port from the access point to the BMC is reachable, default `443`.
2. **Account permissions**: use a read-only or least-privilege BMC account that can read the Redfish asset inventory.
3. **Certificate requirements**: server TLS certificates are verified by default. If the BMC uses a self-signed certificate and a trusted chain cannot be established, you can explicitly disable verification in the task credential. HTTPS encryption is still used after disabling, but BMC identity cannot be verified, which introduces man-in-the-middle risk.
4. **Target constraint**: one target IP must expose only one `ComputerSystem`, to match the "one IP, one physical server asset" instance rule.

### Credential Fields (Redfish method)
- `host`: BMC management-port IP, also the source of the unified instance name.
- `port`: Redfish HTTPS port, default `443`.
- `username`: Redfish/BMC username.
- `password`: Redfish/BMC password. Encrypted at rest and referenced via an environment variable when dispatched.
- `verify_tls`: Whether to verify the server certificate, default `true`; disable only when connecting a self-signed certificate on a trusted management network.

### Collected Data (Redfish method)
| Key | Redfish source | Description |
| :--- | :--- | :--- |
| ip_addr | Collection target | BMC management-port IP |
| port | Collection config | Redfish HTTPS port |
| serial_number | ComputerSystem.SerialNumber | Chassis serial number |
| model | ComputerSystem.Model | Product model |
| brand | ComputerSystem.Manufacturer | Vendor |
| asset_code | ComputerSystem.AssetTag | Asset tag |
| cpu_vendor | First CPU Processor.Manufacturer | CPU vendor |
| cpu_model | First CPU Processor.Model | CPU model |
| cpu_cores | Sum of CPU Processor.TotalCores | CPU physical core count, stored as `cpu_core` |
| cpu_threads | Sum of CPU Processor.TotalThreads | CPU thread count |
| cpu_arch | First CPU InstructionSet | CPU architecture |
| board_vendor | SystemBoard Assembly.Vendor | Motherboard vendor |
| board_model | SystemBoard Assembly.Model | Motherboard model |
| board_serial | SystemBoard Assembly.SerialNumber | Motherboard serial number |
| power_state | ComputerSystem.PowerState | Power state. `On`/`Off` are case-normalized; other non-empty values are kept |
| health | ComputerSystem.Status.Health | Health snapshot. Only `OK`/`Warning`/`Critical`/`Unknown` |

**Related children (attached under the physical server by containment/association)**
- `memory`: `mem_locator`, `mem_part_number`, `mem_type`, `mem_size` (integer GB), `mem_sn`
- `disk`: `disk_vendor`, `disk` (integer GB), `disk_type`, `disk_sn`, `health` (`Status.Health`; Absent drives are skipped), `disk_life_percent` (`PredictedMediaLifeLeftPercent`)
- `nic`: `nic_mac`, `nic_vendor`, `nic_model`, `nic_type`, `nic_iface` (function/adapter `Name` or `Id`), `nic_speed_mbps` (current link speed, otherwise max speed)
- `gpu`: `gpu_name`, `gpu_type`, `gpu_desc`
- `storage_controller`: `sc_id` (`Id`, otherwise `MemberId`), `sc_name`, `sc_vendor`, `sc_model`, `sc_sn`, `sc_firmware`, `health` (`Storage.StorageControllers`)
- `psu`: `psu_name`, `psu_vendor`, `psu_model`, `psu_sn`, `psu_capacity_watts`, `health` (`Power.PowerSupplies`; instantaneous power is not stored)

> Note: child instances attach to the BMC IP; `nic_pci_addr` is omitted; if no SystemBoard is present, `board_*` fields are not written; missing standard fields stay empty; a missing `Power` or `StorageControllers` resource skips that child and the task still succeeds; missing children are not auto-deleted; OEM, EthernetInterfaces, fans, and energy/temperature/voltage/RPM are not collected.
