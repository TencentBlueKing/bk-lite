export const useStorageConfig = () => {
  return {
    instance_type: 'storage',
    dashboardDisplay: [
      {
        indexId: 'device_cpu_usage',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'device_memory_usage',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'device_total_incoming_traffic',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'device_total_outgoing_traffic',
        displayType: 'single',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'snmp_uptime',
        displayType: 'lineChart',
        sortIndex: 4,
        displayDimension: [],
        style: {
          height: '200px',
          width: '49%'
        }
      },
      {
        indexId: 'device_temperature_celsius',
        displayType: 'lineChart',
        sortIndex: 5,
        displayDimension: ['descr'],
        style: {
          height: '200px',
          width: '49%'
        }
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 6,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifInErrors',
          'ifOutErrors',
          'ifInUcastPkts',
          'ifOutUcastPkts',
          'ifInOctets',
          'ifOutOctets'
        ],
        style: {
          height: '400px',
          width: '100%'
        }
      },
      {
        indexId: 'device_fan_state',
        displayType: 'lineChart',
        sortIndex: 7,
        displayDimension: ['descr'],
        style: {
          height: '200px',
          width: '49%'
        }
      },
      {
        indexId: 'device_psu_state',
        displayType: 'lineChart',
        sortIndex: 8,
        displayDimension: ['descr'],
        style: {
          height: '200px',
          width: '49%'
        }
      },
      {
        indexId: 'device_disk_state',
        displayType: 'lineChart',
        sortIndex: 9,
        displayDimension: ['descr'],
        style: {
          height: '200px',
          width: '49%'
        }
      },
      {
        indexId: 'device_raid_state',
        displayType: 'lineChart',
        sortIndex: 10,
        displayDimension: ['descr'],
        style: {
          height: '200px',
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
    },
  };
};
