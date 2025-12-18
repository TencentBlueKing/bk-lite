export const useHardwareConfig = () => {
  return {
    instance_type: 'hardware_server',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'ipmi_power_watts' },
      { type: 'value', key: 'ipmi_temperature_celsius' },
      { type: 'value', key: 'ipmi_voltage_volts' },
    ],
    groupIds: {},
    collectTypes: {
      'Hardware Server SNMP General': 'snmp',
      'Hardware Server IPMI': 'ipmi',
    },
  };
};
