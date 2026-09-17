export const useMerakiDeviceConfig = () => {
  return {
    instance_type: 'cisco_meraki',
    dashboardDisplay: [
      {
        indexId: 'meraki_device_availability_status',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_device_uplink_latency_ms',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'meraki_device_uplink_loss_percent',
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
      'Cisco Meraki': 'http'
    }
  };
};
