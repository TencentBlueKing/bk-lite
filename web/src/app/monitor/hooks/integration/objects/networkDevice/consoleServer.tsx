export const useConsoleServerConfig = () => {
  return {
    instance_type: 'console_server',
    dashboardDisplay: [
      {
        indexId: 'snmp_uptime',
        displayType: 'lineChart',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%'
        }
      },
      {
        indexId: 'device_total_incoming_traffic',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '30%'
        }
      },
      {
        indexId: 'device_total_outgoing_traffic',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '30%'
        }
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifInOctets',
          'ifOutOctets'
        ],
        style: {
          height: '400px',
          width: '100%'
        }
      }
    ],
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id']
    },
    collectTypes: {
      'ConsoleServer Opengear SNMP': 'snmp_opengear',
      'ConsoleServer WTI SNMP': 'snmp_wti',
      'ConsoleServer Avocent ACS SNMP': 'snmp_avocent',
      'ConsoleServer Perle IOLAN SNMP': 'snmp_perle',
      'ConsoleServer Raritan SX SNMP': 'snmp_raritan',
      'ConsoleServer Lantronix SLC SNMP': 'snmp_lantronix'
    }
  };
};
