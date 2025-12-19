export const useSnmpTrapConfig = () => {
  return {
    instance_type: 'snmp_trap',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    collectTypes: {
      'SNMP Trap': 'trap',
    },
  };
};
