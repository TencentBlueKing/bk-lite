### Overview
This plugin discovers network devices and their interfaces via SNMP (optionally discovering inter-device topology) and syncs them to CMDB in a standardized form. Collection is **read-only** and does not modify any device configuration. Collection is agentless: the "access point" you select connects directly to the device.

This document has two parts:
1. Procedure for network operators (how to prepare and configure).
2. Field dictionary (meanings of fields collected into CMDB).

### Entry Point and Execution Location
In the CMDB Web UI:
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Network Device** plugin.
3. Click "Add Task", fill in the steps, and save.

Note: the task actually runs on the "access point" you select; connectivity self-check commands should be run on the access point host.

### Prerequisites
1. **Network connectivity**: `161/UDP` from the access point to the device is reachable.
2. **SNMP enabled on the device**: the device must enable SNMP v2c or v3 and grant a read-only community (v2c) or a read-only account (v3).
3. **Credential preparation**: based on the SNMP version, prepare the corresponding community (v2c) or account and auth/encrypt parameters (v3).

### Procedure
#### Step 1: Network connectivity self-check (run on the access point)
SNMP uses UDP. Port reachability can be checked as follows (use the actual tools available):
- Linux：`nc -vzu <device_ip> 161`
- If the access point has Net-SNMP tools, you can verify v2c directly: `snmpget -v2c -c <community> <device_ip> sysDescr.0`

Pass criterion: returning basic information such as device sysDescr means the SNMP path and credential are usable.

#### Step 2: Fill in the task (page operation)
When adding a task, focus on SNMP version and credentials: first select `version`, then fill in the corresponding fields for that version (see "Credential Fields" below). To discover inter-device topology, enable the parameter `has_network_topo`.

#### Step 3: Verify results
- After saving and running, check the `Added / Updated / Deleted` summary in the task details. In CMDB you should be able to query `network` devices and their `interface` instances.
- If the inventory is incomplete or collection fails, the community/account usually lacks read-only permission, the SNMP version does not match, or `161/UDP` is not open. Recollect after checking.

### Credential Fields
SNMP credentials differ by version. Determine `version` first, then fill in the corresponding fields.

**Common parameters (required for both v2c and v3)**
- `version`: SNMP version, `v2c` or `v3`.
- `snmp_port`: SNMP port, default `161`.
- `timeout`: Per-request timeout.
- `retries`: Request retry count.

**v2c only**
- `community`: Read-only community name, equivalent to a password. Encrypted at rest. Prefer a dedicated read-only community; do not reuse a writable community.

**v3 only**
- `username`: SNMP v3 username.
- `level`: Security level, `authNoPriv` (auth only, no encryption) or `authPriv` (auth + encryption).
- `integrity`: Auth algorithm, `md5` or `sha`.
- `authkey`: Auth key, length must be ≥ 8. Encrypted at rest.
- `privacy`: Encryption algorithm, `des` or `aes` (used only when `level=authPriv`).
- `privkey`: Privacy key, length must be ≥ 8 (used only when `level=authPriv`). Encrypted at rest.

### Parameter Description
- `has_network_topo`: Whether to enable topology discovery (boolean). When enabled, in addition to collecting interfaces, it also discovers connections between device interfaces (based on ARP table / interface table).

### SOID Matching and Catalog Sync
- Collected `sysObjectID` has leading/trailing whitespace and a leading dot stripped first. If the value is `SNMPv2-SMI::enterprises.N...` or `enterprises.N...`, it is expanded to `1.3.6.1.4.1.N...`.
- Device brand, model, and type prefer an exact match on the full OID; if that misses, longest-prefix match is applied on catalog keys (comparing OID arc count, minimum 7 arcs `1.3.6.1.4.1.<enterprise>`). `1.3.6.1.4.1` is not used as a fallback, and `sysDescr` is not guessed.
- `verified` records come from reviewable vendor official product MIBs or product documentation; `legacy-compatible` records retain historical identification capability and do not represent the same level of public product-identity evidence. Enterprise-prefix rows identify the vendor, with model `未知`.
- Before upgrade, run `python manage.py init_oid --dry-run` to see a stably sorted full diff, including additions and their target values, before/after values of updated fields, user overrides, leftover items outside the catalog, and summary counts. This command does not write to the database.
- A normal `batch_init` or `python manage.py init_oid` idempotently syncs the built-in catalog: every startup resets `built_in=True` rows to catalog values, adds missing items, corrects built-in items in place, and keeps unchanged items and leftover items outside the catalog. Repeated sync does not delete-and-recreate records.
- A POST for the same OID is rejected by the API. User overrides can only UPDATE an existing row and set `built_in=False`; such records always take precedence, are reported as "user override", and are not rewritten.
- `--force` is retained only for compatibility with old automation. It still performs a safe full comparison and does not delete or recreate built-in records.
- Unknown SOIDs keep the original OID, brand and model are marked `未知`, and device type is treated as `switch` for compatibility.

#### Release, verification, and rollback
1. Before release, run `python manage.py init_oid --dry-run` on the version to be upgraded and a database copy. Focus on device-type changes, user overrides, and leftover items outside the catalog.
2. Back up the database before production sync, and confirm the backup covers `OidMapping` data and user-defined SOIDs. Keep the dry-run output as a change-audit record.
3. After release, run a normal `batch_init` (or `python manage.py init_oid` alone), then run `--dry-run` again. There should be no additions or updates; synced built-in items other than user overrides should count as unchanged, and custom items should still count as user overrides.
4. Rolling back the application version does not automatically reverse already-corrected built-in mappings. To restore old mappings, restore `OidMapping` data from the pre-sync database backup. User-defined records are not overwritten by sync, but should still be included in the same backup and verification process.

### Collected Data (Field Dictionary)
**Network device (network)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name (form `{ip}-device type`) |
| ip_addr | Device management IP |
| soid | sysObjectID (SNMP standard device object identifier), used to match device model, brand, and type in the OID catalog; unknown SOIDs keep the original OID, brand and model are marked `未知`, and device type is treated as `switch` for compatibility |
| port | SNMP port |
| sysdescr | Device system description (sysDescr) |
| sysname | Device system name (sysName) |
| syslocation | Device location (sysLocation) |
| syscontact | Contact information (sysContact) |
| model | Device model (from OID catalog match) |
| brand | Device brand |

**Interface (interface, related child of network)**

| Key | Description |
| :--- | :--- |
| inst_name | Interface instance display name |
| name | Interface alias / description |
| mac | Interface MAC address |
| status | Interface status (UP / Down / Testing) |
| mtu | Interface MTU |
| speed | Interface speed |
| admin_status | Administrative status |
| oper_status | Operational status |

**Relationships**
- `interface belong network`: Interface belongs to the device.
- `interface connect interface`: Inter-interface connection (discovered only when `has_network_topo` is enabled, based on ARP table / interface table).

> Note: `model` and `brand` depend on matching `soid` (sysObjectID) in the OID catalog; fields such as `syslocation` and `syscontact` are empty when the device has not configured them.
