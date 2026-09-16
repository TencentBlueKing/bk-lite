export const useCiscoMerakiConfig = () => {
  return {
    instance_type: 'cisco_meraki',
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
      },
      {
        indexId: 'meraki_device_inventory_count',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_wireless_ap_count',
        displayType: 'single',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_switch_port_active_count',
        displayType: 'single',
        sortIndex: 4,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_appliance_vpn_network_count',
        displayType: 'single',
        sortIndex: 5,
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
