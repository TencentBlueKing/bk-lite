export const useMerakiApplianceInventoryConfig = () => {
  return {
    instance_type: 'cisco_meraki_appliance',
    dashboardDisplay: [
      {
        indexId: 'meraki_appliance_connect_status',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_appliance_vpn_network_count',
        displayType: 'single',
        sortIndex: 1,
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
