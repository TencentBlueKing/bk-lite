export const useWanoptConfig = () => {
  return {
    instance_type: 'wanopt',
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
          width: '100%'
        }
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 5,
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
      }
    ],
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id']
    },
    collectTypes: {
      'Wanopt Exinda SNMP': 'snmp_exinda',
      'Wanopt Riverbed SNMP': 'snmp_riverbed',
      'Wanopt BlueCoat SNMP': 'snmp_bluecoat'
    }
  };
};
