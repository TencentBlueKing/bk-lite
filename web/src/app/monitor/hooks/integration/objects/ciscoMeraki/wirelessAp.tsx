export const useMerakiWirelessApConfig = () => {
  return {
    instance_type: 'cisco_meraki_wireless_ap',
    dashboardDisplay: [
      {
        indexId: 'meraki_wireless_ap_upstream_loss_percent',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_wireless_ap_downstream_loss_percent',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_wireless_ap_ethernet_speed_mbps',
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
      'Cisco Meraki Wireless AP': 'http'
    }
  };
};
