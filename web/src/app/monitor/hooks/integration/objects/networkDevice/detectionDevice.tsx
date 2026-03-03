export const useDetectionDeviceConfig = () => {
  return {
    instance_type: 'detection_device',
    dashboardDisplay: [
      {
        indexId: 'interface_ifOutDiscards',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'interface_ifOperStatus',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'interface_ifInErrors',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifInErrors',
          'ifOutErrors',
          'ifInUcastPkts',
          'ifOutUcastPkts',
          'ifInOctets',
          'ifOutOctets',
        ],
        style: {
          height: '400px',
          width: '100%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'value', key: 'interface_ifOperStatus' },
      { type: 'value', key: 'interface_ifInErrors' },
      { type: 'value', key: 'interface_ifOutDiscards' },
    ],
    groupIds: {},
    collectTypes: {
      'Detection Device SNMP General': 'snmp',
    },
  };
};
