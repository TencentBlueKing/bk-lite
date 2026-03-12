export const useFirewallConfig = () => {
  return {
    instance_type: 'firewall',
    dashboardDisplay: [
      {
        indexId: 'device_total_outgoing_traffic',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'snmp_uptime',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%'
        }
      },
      {
        indexId: 'device_total_incoming_traffic',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%'
        }
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
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
    tableDiaplay: [
      { type: 'value', key: 'snmp_uptime' },
      { type: 'value', key: 'device_total_incoming_traffic' },
      { type: 'value', key: 'device_total_outgoing_traffic' }
    ],
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id']
    },
    collectTypes: {
      'Firewall SNMP General': 'snmp'
    }
  };
};
