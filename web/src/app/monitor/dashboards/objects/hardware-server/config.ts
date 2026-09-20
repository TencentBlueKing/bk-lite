import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

export const HEALTH_ENUM = {
  1: { label: 'OK', color: '#27c274' },
  2: { label: 'Warning', color: '#faad14' },
  3: { label: 'Critical', color: '#ff4d4f' }
};

export const POWER_ENUM = {
  0: { label: 'Off', color: '#ff4d4f' },
  1: { label: 'On', color: '#27c274' },
  2: { label: 'Other', color: '#faad14' }
};

export const LINK_ENUM = {
  0: { label: 'Down', color: '#ff4d4f' },
  1: { label: 'Up', color: '#27c274' }
};

const REDFISH = "instance_type='hardware_server', collect_type='redfish', __$labels__";
const IPMI_TEMP = 'ipmi_sensor_value{instance_type=\'hardware_server\', unit="degrees_c", __$labels__}';
const IPMI_WATTS = 'ipmi_sensor_value{instance_type=\'hardware_server\', unit="watts", __$labels__}';
const IPMI_RPM = 'ipmi_sensor_value{instance_type=\'hardware_server\', unit="rpm", __$labels__}';

const HEALTH_GUIDE = [
  {
    label: 'OK / Warning / Critical',
    detail: '来自 DMTF Redfish Status.Health：1=OK、2=Warning、3=Critical。戴尔 System.Embedded.1 与浪潮 / 联想 Systems/1 共用同一套编码。'
  }
];

/**
 * Hardware Server 专业盘：Redfish 整机健康 + 热功耗 + 风扇/电源/网口/存储子系统。
 * 温度 / 风扇 / 整机功耗对 IPMI 同类物理量做 PromQL `or` 回退；Redfish 独有健康卡无数据时隐藏。
 * 不按品牌拆盘，也不逐盘 GET。
 */
export const HARDWARE_SERVER_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'hardware-server',
  pageTitle: '硬件服务器监控仪表盘',
  objectFallbackName: 'Hardware Server',
  instanceType: 'hardware_server',
  collectionStatusQuery:
    "count({instance_type='hardware_server', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'redfish'],
  metrics: [
    {
      name: 'redfish_system_health',
      display_name: '系统健康',
      description: '整机 ComputerSystem.Status.Health。',
      unit: 'none',
      query: `max by (instance_id) (redfish_system_health{${REDFISH}})`,
      color: '#27c274'
    },
    {
      name: 'redfish_system_power_state',
      display_name: '电源状态',
      description: 'ComputerSystem.PowerState：On=1、Off=0。',
      unit: 'none',
      query: `max by (instance_id) (redfish_system_power_state{${REDFISH}})`,
      color: '#2f6bff'
    },
    {
      name: 'redfish_manager_health',
      display_name: 'BMC 健康',
      description: 'Manager.Status.Health。',
      unit: 'none',
      query: `max by (instance_id) (redfish_manager_health{${REDFISH}})`,
      color: '#13c2c2'
    },
    {
      name: 'redfish_processor_health_rollup',
      display_name: '处理器健康',
      description: 'ProcessorSummary.Status 汇总，不枚举每颗 CPU。',
      unit: 'none',
      query: `max by (instance_id) (redfish_processor_health_rollup{${REDFISH}})`,
      color: '#597ef7'
    },
    {
      name: 'redfish_memory_health_rollup',
      display_name: '内存健康',
      description: 'MemorySummary.Status 汇总，不枚举每条 DIMM。',
      unit: 'none',
      query: `max by (instance_id) (redfish_memory_health_rollup{${REDFISH}})`,
      color: '#8a5cff'
    },
    {
      name: 'redfish_power_consumed_watts',
      display_name: '整机功耗',
      description: 'PowerControl.PowerConsumedWatts；无 Redfish 样本时回退 IPMI 功率传感器。',
      unit: 'watts',
      query: `max by (instance_id) (redfish_power_consumed_watts{${REDFISH}} or ${IPMI_WATTS})`,
      color: '#ff8a1f'
    },
    {
      name: 'redfish_firmware_info',
      display_name: '固件',
      description: '值为 1，BMC FirmwareVersion 与 BIOS 版本在标签上。',
      unit: 'none',
      query: `max by (bmc_firmware, bios_version) (redfish_firmware_info{${REDFISH}})`,
      color: '#597ef7'
    },
    {
      name: 'redfish_temperature_celsius',
      display_name: '温度',
      description: 'Thermal.Temperatures 各传感器；无 Redfish 样本时回退 IPMI 温度传感器。',
      unit: 'celsius',
      query: `max by (name) (redfish_temperature_celsius{${REDFISH}} or ${IPMI_TEMP})`,
      color: '#f5222d'
    },
    {
      name: 'redfish_fan_speed',
      display_name: '风扇转速',
      description: 'Thermal.Fans.Reading；无 Redfish 样本时回退 IPMI 风扇转速。',
      unit: 'none',
      query: `max by (name) (redfish_fan_speed{${REDFISH}} or ${IPMI_RPM})`,
      color: '#13c2c2'
    },
    {
      name: 'redfish_fan_health',
      display_name: '风扇健康',
      description: 'Thermal.Fans.Status.Health。',
      unit: 'none',
      query: `max by (name) (redfish_fan_health{${REDFISH}})`,
      color: '#27c274'
    },
    {
      name: 'redfish_psu_health',
      display_name: '电源健康',
      description: 'PowerSupplies.Status.Health。',
      unit: 'none',
      query: `max by (name) (redfish_psu_health{${REDFISH}})`,
      color: '#722ed1'
    },
    {
      name: 'redfish_psu_input_watts',
      display_name: '电源输入功率',
      description: 'PowerSupplies.PowerInputWatts。',
      unit: 'watts',
      query: `max by (name) (redfish_psu_input_watts{${REDFISH}})`,
      color: '#ff8a1f'
    },
    {
      name: 'redfish_psu_input_voltage',
      display_name: '电源输入电压',
      description: 'PowerSupplies.LineInputVoltage。',
      unit: 'volts',
      query: `max by (name) (redfish_psu_input_voltage{${REDFISH}})`,
      color: '#d48806'
    },
    {
      name: 'redfish_storage_health',
      display_name: '存储子系统健康',
      description: 'Storage.Status.HealthRollup，不逐盘 GET。',
      unit: 'none',
      query: `max by (id) (redfish_storage_health{${REDFISH}})`,
      color: '#2f6bff'
    },
    {
      name: 'redfish_storage_controller_health',
      display_name: '存储控制器健康',
      description: '内嵌 StorageControllers[].Status。',
      unit: 'none',
      query: `max by (id, storage_id) (redfish_storage_controller_health{${REDFISH}})`,
      color: '#597ef7'
    },
    {
      name: 'redfish_nic_port_link_up',
      display_name: '网口链路',
      description: 'NetworkPort.LinkStatus：Up=1、Down=0。',
      unit: 'none',
      query: `max by (adapter_id, id) (redfish_nic_port_link_up{${REDFISH}})`,
      color: '#27c274'
    },
    {
      name: 'redfish_nic_port_health',
      display_name: '网口健康',
      description: 'NetworkPort.Status.Health。',
      unit: 'none',
      query: `max by (adapter_id, id) (redfish_nic_port_health{${REDFISH}})`,
      color: '#13c2c2'
    },
    {
      name: 'redfish_nic_port_speed_mbps',
      display_name: '网口速率',
      description: 'CurrentLinkSpeedMbps。',
      unit: 'none',
      query: `max by (adapter_id, id) (redfish_nic_port_speed_mbps{${REDFISH}})`,
      color: '#2f6bff'
    }
  ],
  summaryCards: [
    {
      title: '系统健康',
      metric: 'redfish_system_health',
      color: '#27c274',
      icon: 'health',
      enumMap: HEALTH_ENUM,
      hideTrend: true,
      hideWhenNoData: true,
      guide: HEALTH_GUIDE
    },
    {
      title: '电源状态',
      metric: 'redfish_system_power_state',
      color: '#2f6bff',
      icon: 'thunder',
      enumMap: POWER_ENUM,
      hideTrend: true,
      hideWhenNoData: true,
      guide: [
        {
          label: 'On / Off',
          detail: 'Redfish ComputerSystem.PowerState。On=1、Off=0；其它状态归为 Other。'
        }
      ]
    },
    {
      title: 'BMC 健康',
      metric: 'redfish_manager_health',
      color: '#13c2c2',
      icon: 'node',
      enumMap: HEALTH_ENUM,
      hideTrend: true,
      hideWhenNoData: true,
      guide: HEALTH_GUIDE
    },
    {
      title: '整机功耗',
      metric: 'redfish_power_consumed_watts',
      unit: 'watts',
      color: '#ff8a1f',
      icon: 'thunder',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: '整机功耗',
          detail: 'Power.PowerControl.PowerConsumedWatts。无 Redfish 样本时回退 IPMI 功率传感器。'
        }
      ]
    },
    {
      title: '处理器健康',
      metric: 'redfish_processor_health_rollup',
      color: '#597ef7',
      icon: 'health',
      enumMap: HEALTH_ENUM,
      hideTrend: true,
      hideWhenNoData: true,
      guide: [
        {
          label: '处理器汇总',
          detail: 'ProcessorSummary.Status 健康汇总，不枚举每颗 CPU。'
        }
      ]
    },
    {
      title: '内存健康',
      metric: 'redfish_memory_health_rollup',
      color: '#8a5cff',
      icon: 'memory',
      enumMap: HEALTH_ENUM,
      hideTrend: true,
      hideWhenNoData: true,
      guide: [
        {
          label: '内存汇总',
          detail: 'MemorySummary.Status 健康汇总，不枚举每条 DIMM。'
        }
      ]
    }
  ],
  charts: [
    {
      title: '温度',
      subtitle: 'Thermal.Temperatures · 按传感器',
      metric: 'redfish_temperature_celsius',
      keepDimensionSeries: true,
      guide: [
        {
          label: '温度',
          detail: '进风口与 CPU 等温度传感器。UpperThresholdCritical 在指标页可查，本图按传感器分线。'
        }
      ],
      series: [{ metric: 'redfish_temperature_celsius', label: '温度', color: '#f5222d', unit: 'celsius' }]
    },
    {
      title: '整机功耗',
      subtitle: 'PowerConsumedWatts',
      metric: 'redfish_power_consumed_watts',
      guide: [
        {
          label: '整机功耗',
          detail: '系统当前消耗功率。持续抬升结合风扇转速与进风温度排查负载或散热。'
        }
      ],
      series: [{ metric: 'redfish_power_consumed_watts', label: '系统功耗', color: '#ff8a1f', unit: 'watts' }]
    },
    {
      title: '风扇转速',
      subtitle: 'Thermal.Fans · RPM',
      metric: 'redfish_fan_speed',
      keepDimensionSeries: true,
      guide: [
        {
          label: '风扇转速',
          detail: '各风扇读数。健康状态见右侧表，不在本图叠健康编码。'
        }
      ],
      series: [{ metric: 'redfish_fan_speed', label: '转速', color: '#13c2c2' }]
    },
    {
      title: '固件资产',
      subtitle: 'BMC / BIOS 版本标签',
      metric: 'redfish_firmware_info',
      keepDimensionSeries: true,
      guide: [{ label: '固件', detail: '版本在指标标签上，数值恒为 1。' }],
      series: [{ metric: 'redfish_firmware_info', label: '固件', color: '#597ef7' }]
    },
    {
      title: '风扇健康',
      subtitle: '按风扇',
      metric: 'redfish_fan_health',
      keepDimensionSeries: true,
      guide: HEALTH_GUIDE,
      series: [{ metric: 'redfish_fan_health', label: '健康', color: '#27c274' }]
    },
    {
      title: '电源健康',
      subtitle: '按电源模块',
      metric: 'redfish_psu_health',
      keepDimensionSeries: true,
      guide: HEALTH_GUIDE,
      series: [{ metric: 'redfish_psu_health', label: '健康', color: '#722ed1' }]
    },
    {
      title: '电源输入功率',
      subtitle: '按电源模块',
      metric: 'redfish_psu_input_watts',
      keepDimensionSeries: true,
      guide: [{ label: '输入功率', detail: '热备电源输入功率通常接近 0。' }],
      series: [{ metric: 'redfish_psu_input_watts', label: '输入功率', color: '#ff8a1f', unit: 'watts' }]
    },
    {
      title: '电源输入电压',
      subtitle: '按电源模块',
      metric: 'redfish_psu_input_voltage',
      keepDimensionSeries: true,
      guide: [{ label: '输入电压', detail: 'LineInputVoltage。' }],
      series: [{ metric: 'redfish_psu_input_voltage', label: '输入电压', color: '#d48806', unit: 'volts' }]
    },
    {
      title: '存储健康',
      subtitle: '按存储子系统',
      metric: 'redfish_storage_health',
      keepDimensionSeries: true,
      guide: [
        {
          label: '存储子系统',
          detail: 'HealthRollup 覆盖控制器/子系统故障。当前采集禁止 /drives，不展示逐盘健康。'
        }
      ],
      series: [{ metric: 'redfish_storage_health', label: '健康', color: '#2f6bff' }]
    },
    {
      title: '控制器健康',
      subtitle: '内嵌控制器',
      metric: 'redfish_storage_controller_health',
      keepDimensionSeries: true,
      guide: HEALTH_GUIDE,
      series: [{ metric: 'redfish_storage_controller_health', label: '健康', color: '#597ef7' }]
    },
    {
      title: '网口链路',
      subtitle: 'NetworkPorts',
      metric: 'redfish_nic_port_link_up',
      keepDimensionSeries: true,
      guide: [{ label: '链路', detail: 'LinkUp=1、LinkDown/NoLink=0。来自 Chassis NetworkAdapters，不爬 EthernetInterfaces。' }],
      series: [{ metric: 'redfish_nic_port_link_up', label: '链路', color: '#27c274' }]
    },
    {
      title: '网口健康',
      subtitle: 'NetworkPorts',
      metric: 'redfish_nic_port_health',
      keepDimensionSeries: true,
      guide: HEALTH_GUIDE,
      series: [{ metric: 'redfish_nic_port_health', label: '健康', color: '#13c2c2' }]
    },
    {
      title: '网口速率',
      subtitle: 'Mbps',
      metric: 'redfish_nic_port_speed_mbps',
      keepDimensionSeries: true,
      guide: [{ label: '速率', detail: 'CurrentLinkSpeedMbps。' }],
      series: [{ metric: 'redfish_nic_port_speed_mbps', label: '速率', color: '#2f6bff' }]
    }
  ],
  details: []
};
