export const useMerakiOrganizationConfig = () => {
  return {
    instance_type: 'cisco_meraki_organization',
    dashboardDisplay: [
      {
        indexId: 'meraki_org_connect_status',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_org_network_count',
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
      'Cisco Meraki Organization': 'http'
    }
  };
};
