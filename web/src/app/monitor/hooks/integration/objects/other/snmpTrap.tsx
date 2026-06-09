export const useSnmpTrapConfig = () => {
  return {
    instance_type: 'snmp_trap',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'SNMP Trap': 'trap',
    },
  };
};
