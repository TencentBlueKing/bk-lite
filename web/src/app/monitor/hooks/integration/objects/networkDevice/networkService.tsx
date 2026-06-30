export const useNetworkServiceConfig = () => {
  return {
    instance_type: 'network_service',
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
          'ifHCInOctets',
          'ifHCOutOctets'
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
      'NetworkService Infoblox SNMP': 'snmp_infoblox',
      'NetworkService Gigamon SNMP': 'snmp_gigamon',
      'NetworkService Accedian SNMP': 'snmp_accedian',
      'NetworkService ZDNS SNMP': 'snmp_zdns'
    }
  };
};
