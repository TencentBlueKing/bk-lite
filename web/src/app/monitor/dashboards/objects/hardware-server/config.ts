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
      description: '整机健康状态。',
      unit: 'none',
      query: `max by (instance_id) (redfish_system_health_gauge{${REDFISH}})`,
      color: '#27c274'
    },
    {
      name: 'redfish_system_power_state',
      display_name: '电源状态',
      description: '整机电源开/关状态。',
      unit: 'none',
      query: `max by (instance_id) (redfish_system_power_state_gauge{${REDFISH}})`,
      color: '#2f6bff'
    },
    {
      name: 'redfish_manager_health',
      display_name: 'BMC 健康',
      description: 'BMC 管理控制器健康。',
      unit: 'none',
      query: `max by (instance_id) (redfish_manager_health_gauge{${REDFISH}})`,
      color: '#13c2c2'
    },
    {
      name: 'redfish_processor_health_rollup',
      display_name: '处理器健康',
      description: '全部 CPU 的汇总健康。',
      unit: 'none',
      query: `max by (instance_id) (redfish_processor_health_rollup_gauge{${REDFISH}})`,
      color: '#597ef7'
    },
    {
      name: 'redfish_memory_health_rollup',
      display_name: '内存健康',
      description: '全部内存的汇总健康。',
      unit: 'none',
      query: `max by (instance_id) (redfish_memory_health_rollup_gauge{${REDFISH}})`,
      color: '#8a5cff'
    },
    {
      name: 'redfish_power_consumed_watts',
      display_name: '整机功耗',
      description: '系统当前消耗功率。',
      unit: 'watts',
      query: `max by (instance_id) (redfish_power_consumed_watts_gauge{${REDFISH}} or ${IPMI_WATTS})`,
      color: '#ff8a1f'
    },
    {
      name: 'redfish_firmware_info',
      display_name: '固件',
      description: 'BMC / BIOS 版本信息。',
      unit: 'none',
      query: `max by (bmc_firmware, bios_version) (redfish_firmware_info_gauge{${REDFISH}})`,
      color: '#597ef7'
    },
    {
      name: 'redfish_temperature_celsius',
      display_name: '温度',
      description: '各温度传感器读数。',
      unit: 'celsius',
      query: `max by (name) (redfish_temperature_celsius_gauge{${REDFISH}} or ${IPMI_TEMP})`,
      color: '#f5222d'
    },
    {
      name: 'redfish_fan_speed',
      display_name: '风扇转速',
      description: '各风扇转速。',
      unit: 'none',
      query: `max by (name) (redfish_fan_speed_gauge{${REDFISH}} or ${IPMI_RPM})`,
      color: '#13c2c2'
    },
    {
      name: 'redfish_fan_health',
      display_name: '风扇健康',
      description: '各风扇健康状态。',
      unit: 'none',
      query: `max by (name) (redfish_fan_health_gauge{${REDFISH}})`,
      color: '#27c274'
    },
    {
      name: 'redfish_psu_health',
      display_name: '电源健康',
      description: '各电源模块健康。',
      unit: 'none',
      query: `max by (name) (redfish_psu_health_gauge{${REDFISH}})`,
      color: '#722ed1'
    },
    {
      name: 'redfish_psu_input_watts',
      display_name: '电源输入功率',
      description: '各电源模块输入功率。',
      unit: 'watts',
      query: `max by (name) (redfish_psu_input_watts_gauge{${REDFISH}})`,
      color: '#ff8a1f'
    },
    {
      name: 'redfish_psu_input_voltage',
      display_name: '电源输入电压',
      description: '各电源模块输入电压。',
      unit: 'volts',
      query: `max by (name) (redfish_psu_input_voltage_gauge{${REDFISH}})`,
      color: '#d48806'
    },
    {
      name: 'redfish_storage_health',
      display_name: '存储子系统健康',
      description: '存储子系统汇总健康。',
      unit: 'none',
      query: `max by (id) (redfish_storage_health_gauge{${REDFISH}})`,
      color: '#2f6bff'
    },
    {
      name: 'redfish_storage_controller_health',
      display_name: '存储控制器健康',
      description: '存储控制器健康。',
      unit: 'none',
      query: `max by (id, storage_id) (redfish_storage_controller_health_gauge{${REDFISH}})`,
      color: '#597ef7'
    },
    {
      name: 'redfish_nic_port_link_up',
      display_name: '网口链路',
      description: '网口链路是否连通。',
      unit: 'none',
      query: `max by (adapter_id, id) (redfish_nic_port_link_up_gauge{${REDFISH}})`,
      color: '#27c274'
    },
    {
      name: 'redfish_nic_port_health',
      display_name: '网口健康',
      description: '网口健康状态。',
      unit: 'none',
      query: `max by (adapter_id, id) (redfish_nic_port_health_gauge{${REDFISH}})`,
      color: '#13c2c2'
    },
    {
      name: 'redfish_nic_port_speed_mbps',
      display_name: '网口速率',
      description: '网口当前链路速率。',
      unit: 'none',
      query: `max by (adapter_id, id) (redfish_nic_port_speed_mbps_gauge{${REDFISH}})`,
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
      guide: [
        {
          label: '系统健康',
          detail: '整机当前健康状态：OK 正常，Warning 警告，Critical 严重。'
        }
      ]
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
          label: '电源状态',
          detail: '整机电源开/关状态：On 开机，Off 关机，Other 其它状态。'
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
      guide: [
        {
          label: 'BMC 健康',
          detail: '管理控制器当前健康状态：OK 正常，Warning 警告，Critical 严重。'
        }
      ]
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
          detail: '系统当前消耗功率。'
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
          label: '处理器健康',
          detail: '全部 CPU 的汇总健康（非单颗）：OK 正常，Warning 警告，Critical 严重。'
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
          label: '内存健康',
          detail: '全部内存的汇总健康（非单条）：OK 正常，Warning 警告，Critical 严重。'
        }
      ]
    }
  ],
  charts: [
    {
      title: '温度',
      subtitle: '按传感器',
      metric: 'redfish_temperature_celsius',
      keepDimensionSeries: true,
      guide: [
        {
          label: '温度',
          detail: '进风口、CPU 等温度传感器，按传感器分线。'
        }
      ],
      series: [{ metric: 'redfish_temperature_celsius', label: '温度', color: '#f5222d', unit: 'celsius' }]
    },
    {
      title: '整机功耗',
      subtitle: '系统功耗',
      metric: 'redfish_power_consumed_watts',
      guide: [
        {
          label: '整机功耗',
          detail: '系统当前消耗功率；持续抬升时结合风扇与进风温度排查。'
        }
      ],
      series: [{ metric: 'redfish_power_consumed_watts', label: '系统功耗', color: '#ff8a1f', unit: 'watts' }]
    },
    {
      title: '风扇转速',
      subtitle: '按风扇 · RPM',
      metric: 'redfish_fan_speed',
      keepDimensionSeries: true,
      guide: [
        {
          label: '风扇转速',
          detail: '各风扇转速；健康状态见右侧表。'
        }
      ],
      series: [{ metric: 'redfish_fan_speed', label: '转速', color: '#13c2c2' }]
    },
    {
      title: '固件资产',
      subtitle: 'BMC / BIOS 版本',
      metric: 'redfish_firmware_info',
      keepDimensionSeries: true,
      guide: [{ label: '固件', detail: '展示 BMC 与 BIOS 版本。' }],
      series: [{ metric: 'redfish_firmware_info', label: '固件', color: '#597ef7' }]
    },
    {
      title: '风扇健康',
      subtitle: '按风扇',
      metric: 'redfish_fan_health',
      keepDimensionSeries: true,
      guide: [
        {
          label: '风扇健康',
          detail: '各风扇健康状态：OK 正常，Warning 警告，Critical 严重。'
        }
      ],
      series: [{ metric: 'redfish_fan_health', label: '健康', color: '#27c274' }]
    },
    {
      title: '电源健康',
      subtitle: '按电源模块',
      metric: 'redfish_psu_health',
      keepDimensionSeries: true,
      guide: [
        {
          label: '电源健康',
          detail: '各电源模块健康状态：OK 正常，Warning 警告，Critical 严重。'
        }
      ],
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
      guide: [{ label: '输入电压', detail: '各电源模块的输入电压。' }],
      series: [{ metric: 'redfish_psu_input_voltage', label: '输入电压', color: '#d48806', unit: 'volts' }]
    },
    {
      title: '存储健康',
      subtitle: '按子系统',
      metric: 'redfish_storage_health',
      keepDimensionSeries: true,
      guide: [
        {
          label: '存储健康',
          detail: '存储子系统汇总健康（不含逐盘）：OK 正常，Warning 警告，Critical 严重。'
        }
      ],
      series: [{ metric: 'redfish_storage_health', label: '健康', color: '#2f6bff' }]
    },
    {
      title: '控制器健康',
      subtitle: '按控制器',
      metric: 'redfish_storage_controller_health',
      keepDimensionSeries: true,
      guide: [
        {
          label: '控制器健康',
          detail: '各存储控制器健康状态：OK 正常，Warning 警告，Critical 严重。'
        }
      ],
      series: [{ metric: 'redfish_storage_controller_health', label: '健康', color: '#597ef7' }]
    },
    {
      title: '网口链路',
      subtitle: '按端口',
      metric: 'redfish_nic_port_link_up',
      keepDimensionSeries: true,
      guide: [
        {
          label: '网口链路',
          detail: '各网口链路状态：Up 连通，Down 断开。'
        }
      ],
      series: [{ metric: 'redfish_nic_port_link_up', label: '链路', color: '#27c274' }]
    },
    {
      title: '网口健康',
      subtitle: '按端口',
      metric: 'redfish_nic_port_health',
      keepDimensionSeries: true,
      guide: [
        {
          label: '网口健康',
          detail: '各网口健康状态：OK 正常，Warning 警告，Critical 严重。'
        }
      ],
      series: [{ metric: 'redfish_nic_port_health', label: '健康', color: '#13c2c2' }]
    },
    {
      title: '网口速率',
      subtitle: 'Mbps',
      metric: 'redfish_nic_port_speed_mbps',
      keepDimensionSeries: true,
      guide: [{ label: '速率', detail: '网口当前链路速率。' }],
      series: [{ metric: 'redfish_nic_port_speed_mbps', label: '速率', color: '#2f6bff' }]
    }
  ],
  details: []
};
