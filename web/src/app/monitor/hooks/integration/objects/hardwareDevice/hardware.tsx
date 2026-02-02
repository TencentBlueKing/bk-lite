export const useHardwareConfig = () => {
  return {
    instance_type: 'hardware_server',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'ipmi_chassis_power_state' },
      { type: 'value', key: 'ipmi_fan_speed_rpm' },
      { type: 'value', key: 'ipmi_temperature_celsius' },
    ],
    groupIds: {},
    collectTypes: {
      'Hardware Server SNMP General': 'snmp',
      'Hardware Server IPMI': 'ipmi',
    },
  };
};
