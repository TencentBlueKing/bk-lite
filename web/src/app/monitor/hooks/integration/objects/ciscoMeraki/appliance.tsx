export const useMerakiApplianceConfig = () => {
  return {
    instance_type: 'cisco_meraki_appliance',
    dashboardDisplay: [
      {
        indexId: 'meraki_appliance_vpn_peer_reachable',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_appliance_vpn_avg_latency_ms',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_appliance_utilization_percent',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      }
    ],
    groupIds: {},
    collectTypes: {
      'Cisco Meraki Appliance': 'http'
    }
  };
};
