export const useHardwareConfig = () => {
  return {
    instance_type: 'hardware_server',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'Hardware Server SNMP General': 'snmp',
      'Hardware Server IPMI': 'ipmi',
    },
  };
};
