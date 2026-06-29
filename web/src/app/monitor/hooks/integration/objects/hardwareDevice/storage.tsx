export const useStorageConfig = () => {
  return {
    instance_type: 'storage',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'Storage IPMI': 'ipmi',
      OceanStor: 'oceanstor',
      'Storage Synology SNMP': 'snmp_synology',
      'Storage MacroSAN SNMP': 'snmp_macrosan',
      'Storage Sugon SNMP': 'snmp_sugon',
    },
  };
};
