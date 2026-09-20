export const useHardwareConfig = () => {
  return {
    instance_type: 'hardware_server',
    dashboardDisplay: [
      {
        indexId: 'redfish_system_health',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'redfish_system_power_state',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'redfish_manager_health',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'redfish_firmware_info',
        displayType: 'single',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'redfish_temperature_celsius',
        displayType: 'lineChart',
        sortIndex: 4,
        displayDimension: ['name'],
        style: {
          height: '200px',
          width: '48%',
        },
      },
      {
        indexId: 'redfish_power_consumed_watts',
        displayType: 'lineChart',
        sortIndex: 5,
        displayDimension: [],
        style: {
          height: '200px',
          width: '48%',
        },
      },
      {
        indexId: 'redfish_fan_speed',
        displayType: 'lineChart',
        sortIndex: 6,
        displayDimension: ['name'],
        style: {
          height: '200px',
          width: '48%',
        },
      },
      {
        indexId: 'redfish_psu_health',
        displayType: 'table',
        sortIndex: 7,
        displayDimension: [],
        style: {
          height: '200px',
          width: '48%',
        },
      },
      {
        indexId: 'redfish_storage_health',
        displayType: 'table',
        sortIndex: 8,
        displayDimension: [],
        style: {
          height: '240px',
          width: '48%',
        },
      },
      {
        indexId: 'redfish_nic_port_link_up',
        displayType: 'table',
        sortIndex: 9,
        displayDimension: [],
        style: {
          height: '240px',
          width: '48%',
        },
      },
    ],
    groupIds: {},
    collectTypes: {
      'Hardware Server SNMP General': 'snmp',
      'Hardware Server IPMI': 'ipmi',
      'Hardware Server Redfish': 'redfish',
    },
  };
};
