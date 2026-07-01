export const useStorageConfig = () => {
  return {
    instance_type: 'storage',
    dashboardDisplay: [
      {
        indexId: 'pure_array_capacity_bytes_gauge',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '19%'
        }
      },
      {
        indexId: 'pure_array_used_bytes_gauge',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '19%'
        }
      },
      {
        indexId: 'pure_array_read_iops_gauge',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '19%'
        }
      },
      {
        indexId: 'infinibox_pool_physical_capacity_bytes_gauge',
        displayType: 'single',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '19%'
        }
      },
      {
        indexId: 'infinibox_volume_read_iops_gauge',
        displayType: 'single',
        sortIndex: 4,
        displayDimension: [],
        style: {
          height: '200px',
          width: '19%'
        }
      },
      {
        indexId: 'pure_array_used_bytes_gauge',
        displayType: 'lineChart',
        sortIndex: 5,
        displayDimension: [],
        style: {
          height: '220px',
          width: '49%'
        }
      },
      {
        indexId: 'infinibox_pool_physical_capacity_bytes_gauge',
        displayType: 'lineChart',
        sortIndex: 6,
        displayDimension: ['pool'],
        style: {
          height: '220px',
          width: '49%'
        }
      }
    ],
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id']
    },
    collectTypes: {
      'Storage IPMI': 'ipmi',
      OceanStor: 'oceanstor',
      'Storage Synology SNMP': 'snmp_synology',
      'Storage MacroSAN SNMP': 'snmp_macrosan',
      'Storage Sugon SNMP': 'snmp_sugon',
      'Storage NetApp SNMP': 'snmp_netapp',
      'Storage Fujitsu SNMP': 'snmp_fujitsu',
      'Storage Inspur SNMP': 'snmp_inspur',
      'Storage CeresData SNMP': 'snmp_ceresdata',
      'Storage Dell SC8000 SNMP': 'snmp_dellsc8000',
      'Storage Dell PowerVault SNMP': 'snmp_dellpowervault',
      'Storage Hikvision SNMP': 'snmp_hikvision',
      Pure: 'pure',
      InfiniBox: 'infinibox',
    },
  };
};
