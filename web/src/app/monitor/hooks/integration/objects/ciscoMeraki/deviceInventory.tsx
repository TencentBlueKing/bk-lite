export const useMerakiDeviceInventoryConfig = () => {
  return {
    instance_type: 'cisco_meraki_device',
    dashboardDisplay: [
      {
        indexId: 'meraki_device_connect_status',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_device_inventory_count',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_device_online_count',
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
      'Cisco Meraki Device': 'http'
    }
  };
};
