// SNMP 网络设备仪表盘能力矩阵核心逻辑（无外部依赖，可被 codegen / 测试 / 仪表盘共用）。
export type ObjectType = 'switch' | 'router' | 'firewall' | 'loadbalance';

export type CapabilityKey =
  | 'uptime'
  | 'cpu'
  | 'memory'
  | 'temperature'
  | 'fan'
  | 'psu'
  | 'session'
  | 'traffic';

// v2 才启用：型号/系列覆盖品牌默认能力。v1 定义但识别函数不读。
export interface ModelFamily {
  key: string;
  match: string[]; // 命中 sysDescr/sysObjectID 的关键字
  capabilities: CapabilityKey[];
}

// 矩阵按 collect_type 收敛（如 'snmp_cisco'）。
export interface CollectTypeCapability {
  collectType: string;
  capabilities: CapabilityKey[];
  modelFamilies?: ModelFamily[]; // v2 预留
}

export type CapabilityMatrix = Record<ObjectType, CollectTypeCapability[]>;

export interface CapabilityResolution {
  matched: boolean;
  collectType?: string;
  capabilities: Set<CapabilityKey>;
}

export const ALL_OBJECT_TYPES: ObjectType[] = ['switch', 'router', 'firewall', 'loadbalance'];

// 每个能力对应的指标名集合：既含后端 metrics.json 原始名（供 codegen 检测），
// 也含仪表盘卡片/图使用的逻辑名（供前端门控反查）。
const UPTIME = ['snmp_uptime'];
const CPU = ['device_cpu_usage'];
const MEMORY = ['device_memory_usage', 'device_memory_used', 'device_memory_free', 'device_memory_total'];
const TEMPERATURE = ['device_temperature_celsius'];
const FAN = ['device_fan_state', 'device_fan_speed'];
const PSU = ['device_psu_state', 'device_voltage_volts'];
const TRAFFIC = [
  'interface_ifHCInOctets',
  'interface_ifInOctets',
  'interface_ifHCOutOctets',
  'interface_ifOutOctets',
  'device_total_incoming_traffic',
  'device_total_outgoing_traffic'
];
const FW_SESSION = [
  'firewall_sessions',
  'firewall_session_utilization',
  'firewall_active_sessions',
  'firewall_current_connections',
  'firewall_active_connections',
  'firewall_tcp_connections',
  'firewall_udp_connections',
  'firewall_pf_states'
];
const LB_SESSION = ['lb_connections', 'lb_current_connections'];

const NETWORK_BASE = {
  uptime: UPTIME,
  cpu: CPU,
  memory: MEMORY,
  temperature: TEMPERATURE,
  fan: FAN,
  psu: PSU,
  traffic: TRAFFIC
};

export const CAPABILITY_METRICS: Record<ObjectType, Record<CapabilityKey, string[]>> = {
  switch: { ...NETWORK_BASE, session: [] },
  router: { ...NETWORK_BASE, session: [] },
  firewall: { ...NETWORK_BASE, session: FW_SESSION },
  loadbalance: { ...NETWORK_BASE, session: LB_SESSION }
};

// 反查：某指标名属于哪个能力；未分类返回 undefined。
export function metricCapability(objectType: ObjectType, metricName: string): CapabilityKey | undefined {
  const groups = CAPABILITY_METRICS[objectType];
  for (const key of Object.keys(groups) as CapabilityKey[]) {
    if (groups[key].includes(metricName)) {
      return key;
    }
  }
  return undefined;
}

// 识别：在矩阵中找 collectType 为 idText 子串者，取最长命中（避免通用 'snmp' 抢先于 'snmp_cisco'）。
export function resolveCapability(
  matrix: CapabilityMatrix,
  objectType: ObjectType,
  idText: string
): CapabilityResolution {
  const entries = [...(matrix[objectType] || [])].sort(
    (a, b) => b.collectType.length - a.collectType.length
  );
  const hit = entries.find((entry) => idText.includes(entry.collectType));
  if (!hit) {
    return { matched: false, capabilities: new Set() };
  }
  return { matched: true, collectType: hit.collectType, capabilities: new Set(hit.capabilities) };
}

// 门控真值表。
export function isMetricVisible(
  resolved: CapabilityResolution,
  objectType: ObjectType,
  metricName: string,
  hasData: boolean
): boolean {
  const cap = metricCapability(objectType, metricName);
  if (cap === undefined) {
    return hasData; // 未分类指标 → 维持现状
  }
  if (!resolved.matched) {
    return hasData; // 未命中品牌 → 回退现状
  }
  if (resolved.capabilities.has(cap)) {
    return true; // 支持 → 渲染（无数据显示 --）
  }
  return false; // 不支持 → 不渲染
}
