export const useMerakiNetworkConfig = () => {
  return {
    instance_type: 'cisco_meraki_organization',
    dashboardDisplay: [
      {
        indexId: 'meraki_network_present',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      }
    ],
    groupIds: {},
    collectTypes: {
      'Cisco Meraki Organization': 'http'
    }
  };
};
