export const useStorageConfig = () => {
  return {
    instance_type: 'storage',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'ipmi_chassis_power_state' },
      { type: 'value', key: 'ipmi_fan_speed_rpm' },
      { type: 'value', key: 'ipmi_temperature_celsius' },
    ],
    groupIds: {},
    collectTypes: {
      'Storage IPMI': 'ipmi',
    },
  };
};
