### Overview
This plugin connects directly to vCenter via pyVmomi and collects vCenter version, ESXi host hardware and version, VM name/IP/specs/cluster membership, datastore name/type/capacity, and host associations. It outputs a unified structure for CMDB ingestion.

This document has two parts:
1. Procedure for non-specialist VMware operators (how to prepare and configure).
2. Field dictionary (meanings of fields collected into CMDB).



### Entry Point and Execution Location
In the CMDB Web UI:
1. Go to "CMDB → Asset Management → Auto Discovery → Collection → Professional Collection".
2. Select the **vCenter** plugin.
3. Click "Add Task", fill in the steps, and save.

Note: the task actually runs on the "access point" you select; connectivity self-check commands should be run on the access point host.



### Prerequisites
1. Network connectivity: `443/TCP` from the access point to vCenter is reachable.
2. Account: create a dedicated collection account, grant Read-only permission, and grant it on parent objects with inheritance (propagate).
3. Asset preparation: if the "vCenter dropdown" on the page is empty, first maintain a vCenter asset in CMDB asset data (including the management address).




### Procedure
### Step 1: Network connectivity self-check (run on the access point)
- Linux：
	- `nc -vz <vcenter_host> 443`
	- `curl -k https://<vcenter_host>:443/ -I`
- Windows PowerShell：
	- `Test-NetConnection <vcenter_host> -Port 443`

Pass criterion: the port is reachable. If `curl` reports a certificate error, that is common; you can temporarily disable SSL verification on the page to validate the flow (see below).


### Step 2: Create a collection task in CMDB (page operation)
When adding a task, focus on the "credential/auth" fields:

- `username`: vCenter login username (prefer a read-only account).
- `password`: Login password for that user.
- `port`: vCenter API port (usually `443`).
- `sslVerify`: Whether to verify the vCenter HTTPS certificate. If vCenter uses a self-signed certificate and the access point does not have the trust chain installed, you can temporarily disable this to validate the flow, then add certificate trust and re-enable it.



### Collected Data (Field Dictionary)
**Vcenter(vmware_vc)**

| Key           | Description |
| :------------ | :--- |
| vc_version    | vCenter version |
| inst_name     | vCenter name (for vc: display its name; in other tables it is name[MOID]) |

**Esxi(vmware_esxi)**

| Key           | Description |
| :------------ | :--- |
| resource_id   | ESXi host MOID |
| inst_name     | Host name[MOID] |
| ip_addr       | Host management IP (prefer vNIC) |
| memory        | Host physical memory (MB) |
| cpu_model     | CPU model |
| cpu_cores     | Physical core count |
| vcpus         | Thread count (logical CPU) |
| esxi_version  | ESXi version |
| vmware_ds     | Accessible datastore MOID list (comma-separated) |

**VM (vmware_vm)**

| Key           | Description |
| :------------ | :--- |
| vmware_vm     | VM object collection key name |
| resource_id   | VM MOID |
| inst_name     | VM name[MOID] |
| ip_addr       | Preferred VM IP (IPv4 first, then IPv6) |
| vmware_esxi   | Hosting ESXi host MOID |
| vmware_ds     | Mounted datastore MOID list (comma-separated) |
| cluster       | Cluster name (if in a cluster) |
| os_name       | Guest OS full name |
| vcpus         | Allocated vCPU count |
| memory        | Allocated memory (MB) |
| annotation    | vCenter annotation (vm.summary.config.annotation) |
| uptime_seconds | Uptime in seconds for this boot (vm.summary.quickStats.uptimeSeconds; 0 if powered off/unavailable) |
| tools_version | VMware Tools version (vm.guest.toolsVersion) |
| tools_status  | VMware Tools install status (vm.guest.toolsStatus) |
| tools_running_status | VMware Tools running status (vm.guest.toolsRunningStatus) |
| last_boot     | Last boot time (vm.runtime.bootTime; None if powered off) |
| creation_date | Creation time (vm.config.createDate; vSphere 6.7+) |
| last_backup   | Last backup time (custom field, e.g. NB_LAST_BACKUP) |
| backup_policy | Backup policy (custom field, e.g. NB_BACKUP_POLICY) |
| data_disks    | Disk detail JSON (per disk: disk_id/provisioned_gb/used_gb/disk_type/datastore; used_gb is null when layoutEx is unavailable) |

**Storage (vmware_ds)**

| Key           | Description |
| :------------ | :--- |
| resource_id   | Datastore MOID |
| inst_name     | Datastore name[MOID] |
| url           | Datastore URL path |
| system_type   | Storage type (VMFS/NFS, etc.) |
| storage       | Total capacity (GB) |
| vmware_esxi   | Associated ESXi host MOID list (comma-separated) |
