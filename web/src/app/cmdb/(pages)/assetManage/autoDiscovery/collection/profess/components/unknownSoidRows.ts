export interface UnresolvedInterface {
  name: string;
  description?: string;
  mac?: string;
  status?: string;
}

export interface UnresolvedDevice {
  soid: string;
  ip_addr: string;
  port?: string;
  sys_desc?: string;
  interfaces?: UnresolvedInterface[];
  device_type?: string;
  brand?: string;
  model?: string;
  mapped?: boolean;
}

export interface UnresolvedGroup {
  soid: string;
  devices?: Array<{
    ip_addr: string;
    port?: string;
    sys_desc?: string;
    interfaces?: UnresolvedInterface[];
  }>;
  device_type?: string;
  brand?: string;
  model?: string;
  mapped?: boolean;
}

export interface SoidRow {
  soid: string;
  count: number;
  device_type: string;
  brand: string;
  model: string;
  locked: boolean;
}

export const NETWORK_DEVICE_TYPES = ['switch', 'router', 'firewall', 'loadbalance'] as const;

const SUCCESS_STATUS = 2;
const PARTIAL_SUCCESS_STATUS = 8;

export function flattenUnresolvedDevices(groups: UnresolvedGroup[] | undefined): UnresolvedDevice[] {
  const devices: UnresolvedDevice[] = [];
  (groups || []).forEach((group) => {
    (group.devices || []).forEach((device) => {
      devices.push({
        soid: group.soid || '',
        ip_addr: device.ip_addr,
        port: device.port,
        sys_desc: device.sys_desc,
        interfaces: device.interfaces || [],
        device_type: group.device_type || '',
        brand: group.brand || '',
        model: group.model || '',
        mapped: Boolean(group.mapped),
      });
    });
  });
  return devices;
}

export function uniqueSoidRows(selectedDevices: UnresolvedDevice[]): SoidRow[] {
  const rows: SoidRow[] = [];
  const indexBySoid = new Map<string, number>();
  selectedDevices.forEach((device) => {
    const soid = device.soid || '';
    const existingIndex = indexBySoid.get(soid);
    if (existingIndex === undefined) {
      indexBySoid.set(soid, rows.length);
      rows.push({
        soid,
        count: 1,
        device_type: device.device_type || '',
        brand: device.brand || '',
        model: device.model || '',
        locked: Boolean(device.mapped),
      });
      return;
    }
    const row = rows[existingIndex];
    row.count += 1;
    if (device.mapped) {
      row.locked = true;
      row.device_type = device.device_type || row.device_type;
      row.brand = device.brand || row.brand;
      row.model = device.model || row.model;
    }
  });
  return rows;
}

export function canOperateUnknownSoid(execStatus: number, selectedCount: number): boolean {
  const terminal = execStatus === SUCCESS_STATUS || execStatus === PARTIAL_SUCCESS_STATUS;
  return terminal && selectedCount > 0;
}
