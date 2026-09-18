import type { MetricUnavailableContract } from './types';

const H3C_TEMP_GUIDE =
  '华三 H3C（HH3C-ENTITY-EXT-MIB hh3cEntityExtTemperature）对没有温度传感器的硬件实体会上报 65535（16 位整数上限）表示不支持/不可用，这不是真实温度。仪表盘识别后显示「无传感器」。若显示「--」，表示当前时间窗口内没有采到温度数据。';

const H3C_VOLTAGE_GUIDE =
  '华三 H3C（hh3cEntityExtVoltage）以毫伏上报，看板按 /1000 换算为伏特；65535 表示该实体无电压传感器/不支持。识别后显示「无传感器」，与「--」（无数据）区分。';

const ALLIED_TEMP_GUIDE =
  'Allied Telesis（atEnvMonv2TemperatureCurrent）用 128 / -128 表示无效读数。仪表盘识别后显示「无传感器」，不会把哨兵计入最高温度。';

const OPTICAL_NO_MODULE_GUIDE =
  '光模块未插入或厂商上报「无模块」哨兵时，KPI 显示「无模块」，与「--」（该品牌未采集/窗口内无序列）区分。有效读数已按该品牌插件 metrics.json 换算为 dBm。';

const H3C_FAN_GUIDE =
  '华三风扇状态仅统计 ENTITY-MIB entPhysicalClass=fan(7) 的行，避免把其它实体的 OperStatus 误当成风扇故障。';

const H3C_PSU_GUIDE =
  '华三电源状态仅统计 entPhysicalClass=powerSupply(6) 的行，避免非电源实体污染最坏状态。';

const HUAWEI_FAN_GUIDE =
  '华为风扇状态仅保留 device_fan_present==1 的在位风扇，空槽不计入故障。';

const HUAWEI_PSU_GUIDE =
  '华为电源状态仅保留 device_psu_present==1 的在位电源，空槽不计入故障。';

/**
 * 已证实品牌的哨兵/过滤契约。禁止为未证实品牌预防性注册。
 * evidence 路径相对于仓库根目录。
 */
export const METRIC_UNAVAILABLE_CONTRACTS: readonly MetricUnavailableContract[] = [
  // ── 温度 ──────────────────────────────────────────────
  {
    metric: 'device_temperature_celsius',
    collectType: 'snmp_h3c',
    sentinels: [65535],
    meaning: 'no_sensor',
    displayLabel: '无传感器',
    guideDetail: H3C_TEMP_GUIDE,
    valueExpr: 'device_temperature_celsius{__$labels__} != 65535',
    rawExpr: 'device_temperature_celsius{__$labels__}',
    aggregate: 'max',
    sentinelPolicy: 'keep_for_display',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_h3c/metrics.json'
  },
  {
    metric: 'device_temperature_celsius',
    collectType: 'snmp_alliedtelesis',
    sentinels: [128, -128],
    meaning: 'no_sensor',
    displayLabel: '无传感器',
    guideDetail: ALLIED_TEMP_GUIDE,
    valueExpr: 'device_temperature_celsius{__$labels__} != 128 != -128',
    rawExpr: 'device_temperature_celsius{__$labels__}',
    aggregate: 'max',
    sentinelPolicy: 'keep_for_display',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_alliedtelesis/metrics.json'
  },

  // ── 电压 ──────────────────────────────────────────────
  {
    metric: 'device_voltage_volts',
    collectType: 'snmp_h3c',
    sentinels: [65535],
    meaning: 'no_sensor',
    displayLabel: '无传感器',
    guideDetail: H3C_VOLTAGE_GUIDE,
    valueExpr: '(device_voltage_volts{__$labels__} != 65535) / 1000',
    rawExpr: 'device_voltage_volts{__$labels__}',
    aggregate: 'max',
    sentinelPolicy: 'keep_for_display',
    scaleNote: 'mV → V (/1000)',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_h3c/metrics.json'
  },

  // ── 光功率（分 collect_type，禁止全局 OR）────────────────
  {
    metric: 'device_optical_rx_power',
    collectType: 'snmp_huawei',
    sentinels: [2147483647],
    meaning: 'no_module',
    displayLabel: '无模块',
    guideDetail: OPTICAL_NO_MODULE_GUIDE,
    valueExpr:
      '10 * log10(device_optical_rx_power{__$labels__} / 1000) and (device_optical_rx_power{__$labels__} > 0) and (device_optical_rx_power{__$labels__} != 2147483647)',
    rawExpr: 'device_optical_rx_power{__$labels__}',
    aggregate: 'min',
    sentinelPolicy: 'keep_for_display',
    scaleNote: 'µW → dBm via 10*log10(µW/1000)',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_huawei/metrics.json'
  },
  {
    metric: 'device_optical_tx_power',
    collectType: 'snmp_huawei',
    sentinels: [2147483647],
    meaning: 'no_module',
    displayLabel: '无模块',
    guideDetail: OPTICAL_NO_MODULE_GUIDE,
    valueExpr:
      '10 * log10(device_optical_tx_power{__$labels__} / 1000) and (device_optical_tx_power{__$labels__} > 0) and (device_optical_tx_power{__$labels__} != 2147483647)',
    rawExpr: 'device_optical_tx_power{__$labels__}',
    aggregate: 'min',
    sentinelPolicy: 'keep_for_display',
    scaleNote: 'µW → dBm via 10*log10(µW/1000)',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_huawei/metrics.json'
  },
  {
    metric: 'device_optical_rx_power',
    collectType: 'snmp_ruijie',
    sentinels: [-10000],
    meaning: 'no_module',
    displayLabel: '无模块',
    guideDetail: OPTICAL_NO_MODULE_GUIDE,
    valueExpr: '(device_optical_rx_power{__$labels__} != -10000) / 100',
    rawExpr: 'device_optical_rx_power{__$labels__}',
    aggregate: 'min',
    sentinelPolicy: 'keep_for_display',
    scaleNote: 'raw/100 → dBm',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_ruijie/metrics.json'
  },
  {
    metric: 'device_optical_tx_power',
    collectType: 'snmp_ruijie',
    sentinels: [-10000],
    meaning: 'no_module',
    displayLabel: '无模块',
    guideDetail: OPTICAL_NO_MODULE_GUIDE,
    valueExpr: '(device_optical_tx_power{__$labels__} != -10000) / 100',
    rawExpr: 'device_optical_tx_power{__$labels__}',
    aggregate: 'min',
    sentinelPolicy: 'keep_for_display',
    scaleNote: 'raw/100 → dBm',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_ruijie/metrics.json'
  },
  {
    metric: 'device_optical_rx_power',
    collectType: 'snmp_parks',
    sentinels: [-2147483648],
    meaning: 'no_module',
    displayLabel: '无模块',
    guideDetail: OPTICAL_NO_MODULE_GUIDE,
    valueExpr: '(device_optical_rx_power{__$labels__} != -2147483648) / 100',
    rawExpr: 'device_optical_rx_power{__$labels__}',
    aggregate: 'min',
    sentinelPolicy: 'keep_for_display',
    scaleNote: 'raw/100 → dBm',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_parks/metrics.json'
  },
  {
    metric: 'device_optical_tx_power',
    collectType: 'snmp_parks',
    sentinels: [-2147483648],
    meaning: 'no_module',
    displayLabel: '无模块',
    guideDetail: OPTICAL_NO_MODULE_GUIDE,
    valueExpr: '(device_optical_tx_power{__$labels__} != -2147483648) / 100',
    rawExpr: 'device_optical_tx_power{__$labels__}',
    aggregate: 'min',
    sentinelPolicy: 'keep_for_display',
    scaleNote: 'raw/100 → dBm',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_parks/metrics.json'
  },
  {
    metric: 'device_optical_rx_power',
    collectType: 'snmp_futurematrix',
    sentinels: [2147483647],
    meaning: 'no_module',
    displayLabel: '无模块',
    guideDetail: OPTICAL_NO_MODULE_GUIDE,
    valueExpr:
      '10 * log10(device_optical_rx_power{__$labels__} / 1000) and (device_optical_rx_power{__$labels__} > 0) and (device_optical_rx_power{__$labels__} != 2147483647)',
    rawExpr: 'device_optical_rx_power{__$labels__}',
    aggregate: 'min',
    sentinelPolicy: 'keep_for_display',
    scaleNote: 'µW → dBm via 10*log10(µW/1000)',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_futurematrix/metrics.json'
  },
  {
    metric: 'device_optical_tx_power',
    collectType: 'snmp_futurematrix',
    sentinels: [2147483647],
    meaning: 'no_module',
    displayLabel: '无模块',
    guideDetail: OPTICAL_NO_MODULE_GUIDE,
    valueExpr:
      '10 * log10(device_optical_tx_power{__$labels__} / 1000) and (device_optical_tx_power{__$labels__} > 0) and (device_optical_tx_power{__$labels__} != 2147483647)',
    rawExpr: 'device_optical_tx_power{__$labels__}',
    aggregate: 'min',
    sentinelPolicy: 'keep_for_display',
    scaleNote: 'µW → dBm via 10*log10(µW/1000)',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_futurematrix/metrics.json'
  },

  // ── 风扇 / 电源行集合过滤（对齐插件 query，无哨兵展示）──
  {
    metric: 'device_fan_state',
    collectType: 'snmp_h3c',
    sentinels: [],
    meaning: 'empty_slot',
    displayLabel: '风扇状态',
    guideDetail: H3C_FAN_GUIDE,
    valueExpr: "device_fan_state{__$labels__, entPhysicalClass='7'}",
    aggregate: 'max',
    sentinelPolicy: 'drop_at_query',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_h3c/metrics.json'
  },
  {
    metric: 'device_psu_state',
    collectType: 'snmp_h3c',
    sentinels: [],
    meaning: 'empty_slot',
    displayLabel: '电源状态',
    guideDetail: H3C_PSU_GUIDE,
    valueExpr: "device_psu_state{__$labels__, entPhysicalClass='6'}",
    aggregate: 'max',
    sentinelPolicy: 'drop_at_query',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_h3c/metrics.json'
  },
  {
    metric: 'device_fan_state',
    collectType: 'snmp_huawei',
    sentinels: [],
    meaning: 'empty_slot',
    displayLabel: '风扇状态',
    guideDetail: HUAWEI_FAN_GUIDE,
    valueExpr: 'device_fan_state{__$labels__} and (device_fan_present{__$labels__} == 1)',
    aggregate: 'max',
    sentinelPolicy: 'drop_at_query',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_huawei/metrics.json'
  },
  {
    metric: 'device_psu_state',
    collectType: 'snmp_huawei',
    sentinels: [],
    meaning: 'empty_slot',
    displayLabel: '电源状态',
    guideDetail: HUAWEI_PSU_GUIDE,
    valueExpr: 'device_psu_state{__$labels__} and (device_psu_present{__$labels__} == 1)',
    aggregate: 'max',
    sentinelPolicy: 'drop_at_query',
    evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_huawei/metrics.json'
  }
];
