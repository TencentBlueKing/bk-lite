export const useVoiceGatewayConfig = () => {
  return {
    instance_type: 'voice_gateway',
    dashboardDisplay: [
      {
        indexId: 'snmp_uptime',
        displayType: 'lineChart',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%'
        }
      },
      {
        indexId: 'device_total_incoming_traffic',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '30%'
        }
      },
      {
        indexId: 'device_total_outgoing_traffic',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '30%'
        }
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifInOctets',
          'ifOutOctets'
        ],
        style: {
          height: '400px',
          width: '100%'
        }
      }
    ],
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id']
    },
    collectTypes: {
      'VoiceGateway AudioCodes SNMP': 'snmp_audiocodes',
      'VoiceGateway Ribbon SNMP': 'snmp_ribbon',
      'VoiceGateway Acme Packet SNMP': 'snmp_acmepacket',
      'VoiceGateway Patton SNMP': 'snmp_patton'
    }
  };
};
