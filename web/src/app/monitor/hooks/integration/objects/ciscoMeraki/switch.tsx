export const useMerakiSwitchConfig = () => {
  return {
    instance_type: 'cisco_meraki',
    dashboardDisplay: [
      {
        indexId: 'meraki_switch_port_enabled',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_switch_port_poe_enabled',
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
      'Cisco Meraki': 'http'
    }
  };
};
