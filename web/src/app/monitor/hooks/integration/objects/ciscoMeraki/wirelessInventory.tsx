export const useMerakiWirelessInventoryConfig = () => {
  return {
    instance_type: 'cisco_meraki_wireless_ap',
    dashboardDisplay: [
      {
        indexId: 'meraki_wireless_connect_status',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_wireless_ap_count',
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
      'Cisco Meraki Wireless AP': 'http'
    }
  };
};
