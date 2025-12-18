export const useStorageConfig = () => {
  return {
    instance_type: 'storage',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'ipmi_power_watts' },
      { type: 'value', key: 'ipmi_temperature_celsius' },
      { type: 'value', key: 'ipmi_voltage_volts' },
    ],
    groupIds: {},
    collectTypes: {
      'Storage IPMI': 'ipmi',
    },
  };
};
