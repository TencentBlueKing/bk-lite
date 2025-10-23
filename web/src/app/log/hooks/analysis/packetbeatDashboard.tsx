import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';
import { formatNumericValue } from '@/app/log/utils/common';

export const usePacketbeatDashboard = () => {
  const { t } = useTranslation();

  return {
    name: t('log.analysis.packetbeat.dashboardName'),
    desc: '',
    id: '1',
    filters: {},
    other: {},
    view_sets: [
      {
        h: 3,
        w: 12,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.packetbeat.protocolTrafficDistribution'),
        moved: false,
        static: false,
        description: t(
          'log.analysis.packetbeat.protocolTrafficDistributionDesc'
        ),
        valueConfig: {
          chartType: 'line',
          dataSource: 1,
          displayMaps: {
            type: 'multiple',
            key: 'network.transport',
            value: 'networkbytes',
            tooltipField: 'network.transport',
          },
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (_time:${_time},network.transport) sum(network.bytes) as networkbytes| math networkbytes / 1024 / 1024 / 1024 as networkbytes',
          },
        },
      },
      {
        h: 3,
        w: 6,
        x: 0,
        y: 3,
        i: uuidv4(),
        name: t('log.analysis.packetbeat.totalNetworkTraffic'),
        moved: false,
        static: false,
        description: t('log.analysis.packetbeat.totalNetworkTrafficDesc'),
        valueConfig: {
          chartType: 'line',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: 'networkbytes',
            value: 'networkbytes',
            tooltipField: 'networkbytes',
          },
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (_time:${_time}) sum(network.bytes) as networkbytes | math networkbytes / 1024 / 1024 / 1024 as networkbytes',
          },
        },
      },
      {
        h: 3,
        w: 6,
        x: 6,
        y: 3,
        i: uuidv4(),
        name: t('log.analysis.packetbeat.totalPacketCount'),
        moved: false,
        static: false,
        description: t('log.analysis.packetbeat.totalPacketCountDesc'),
        valueConfig: {
          chartType: 'line',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: 'networkpackets',
            value: 'networkpackets',
            tooltipField: 'networkpackets',
          },
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (_time:${_time}) sum(network.packets) as networkpackets',
          },
        },
      },
      {
        h: 4,
        w: 6,
        x: 0,
        y: 6,
        i: uuidv4(),
        name: t('log.analysis.packetbeat.topSourceIPs'),
        moved: false,
        static: false,
        description: t('log.analysis.packetbeat.topSourceIPsDesc'),
        valueConfig: {
          chartType: 'table',
          dataSource: 1,
          columns: [
            {
              title: t('log.analysis.packetbeat.sourceIP'),
              dataIndex: 'source.ip',
              key: 'source.ip',
            },
            {
              title: t('log.analysis.packetbeat.networkTrafficGB'),
              dataIndex: 'src_bytes',
              key: 'src_bytes',
              render: (val: string) => formatNumericValue(val),
            },
          ],
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (source.ip) sum(network.bytes) as src_bytes | math src_bytes / 1024 / 1024 / 1024 as src_bytes| sort by (src_bytes desc) | limit 20',
          },
        },
      },
      {
        h: 4,
        w: 6,
        x: 6,
        y: 6,
        i: uuidv4(),
        name: t('log.analysis.packetbeat.topDestinationIPs'),
        moved: false,
        static: false,
        description: t('log.analysis.packetbeat.topDestinationIPsDesc'),
        valueConfig: {
          chartType: 'table',
          dataSource: 1,
          columns: [
            {
              title: t('log.analysis.packetbeat.destinationIP'),
              dataIndex: 'destination.ip',
              key: 'destination.ip',
            },
            {
              title: t('log.analysis.packetbeat.networkTrafficGB'),
              dataIndex: 'src_bytes',
              key: 'src_bytes',
              render: (val: string) => formatNumericValue(val),
            },
          ],
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (destination.ip) sum(network.bytes) as src_bytes | math src_bytes / 1024 / 1024 / 1024 as src_bytes| sort by (src_bytes desc) | limit 20',
          },
        },
      },
      {
        h: 6,
        w: 12,
        x: 0,
        y: 10,
        i: uuidv4(),
        name: t('log.analysis.packetbeat.highTrafficSankey'),
        moved: false,
        static: false,
        description: t('log.analysis.packetbeat.highTrafficSankeyDesc'),
        valueConfig: {
          chartType: 'sankey',
          dataSource: 1,
          displayMaps: {
            sourceField: 'source.ip',
            targetField: 'destination.ip',
            valueField: 'flow_bytes',
            tooltipFields: {
              flow_bytes: t('log.analysis.packetbeat.networkTrafficGB'),
              'source.ip': t('log.analysis.packetbeat.sourceIP'),
              'destination.ip': t('log.analysis.packetbeat.destinationIP'),
              'network.transport': t('log.analysis.packetbeat.transport'),
              'source.port': t('log.analysis.packetbeat.sourcePort'),
              'destination.port': t('log.analysis.packetbeat.destinationPort'),
            },
          },
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (source.ip, destination.ip, network.transport, source.port, destination.port) sum(network.bytes) as flow_bytes| math flow_bytes / 1024 / 1024 / 1024 as flow_bytes | sort by (flow_bytes desc) | limit 20',
          },
        },
      },
    ],
  };
};
