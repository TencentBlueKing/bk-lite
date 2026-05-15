import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';
import { formatNumericValue } from '@/app/log/utils/common';

export const usePacketbeatDashboard = () => {
  const { t } = useTranslation();

  return {
    name: t('log.analysis.packetbeat.dashboardName'),
    desc: '',
    id: '1',
    category: 'network',
    categoryName: t('log.analysis.category.network'),
    collectTypeName: 'flows',
    filters: {},
    other: {},
    view_sets: [
      {
        h: 2,
        w: 3,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.packetbeat.totalTrafficVolume'),
        moved: false,
        static: false,
        description: '统计网络总流量，并与上一周期对比。',
        valueConfig: {
          chartType: 'flowKpiCard',
          dataSource: 1,
          metricLabel: t('log.analysis.packetbeat.totalTrafficVolume'),
          displayMaps: {
            type: 'single',
            key: 'networkbytes',
            value: 'networkbytes',
            tooltipField: 'networkbytes'
          },
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (_time:${_time}) sum(network.bytes) as networkbytes | math networkbytes / 1024 / 1024 as networkbytes'
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 3,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.packetbeat.totalPacketVolume'),
        moved: false,
        static: false,
        description: '统计网络总包数，并与上一周期对比。',
        valueConfig: {
          chartType: 'flowKpiCard',
          dataSource: 1,
          color: '#155AEF',
          metricLabel: t('log.analysis.packetbeat.totalPacketVolume'),
          displayMaps: {
            type: 'single',
            key: 'networkpackets',
            value: 'networkpackets',
            tooltipField: 'networkpackets'
          },
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (_time:${_time}) sum(network.packets) as networkpackets'
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.packetbeat.flowRecordCount'),
        moved: false,
        static: false,
        description: '统计流记录总数，并与上一周期对比。',
        valueConfig: {
          chartType: 'flowKpiCard',
          dataSource: 1,
          color: '#15B77E',
          metricLabel: t('log.analysis.packetbeat.flowRecordCount'),
          displayMaps: {
            type: 'single',
            key: 'flowcount',
            value: 'flowcount',
            tooltipField: 'flowcount'
          },
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (_time:${_time}) count() as flowcount'
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.packetbeat.longLivedFlows'),
        moved: false,
        static: false,
        description: '统计长时连接数，并与上一周期对比。',
        valueConfig: {
          chartType: 'flowKpiCard',
          dataSource: 1,
          color: '#f5222d',
          metricLabel: t('log.analysis.packetbeat.longLivedFlows'),
          displayMaps: {
            type: 'single',
            key: 'long_flows',
            value: 'long_flows',
            tooltipField: 'long_flows'
          },
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (_time:${_time}) count() if (event.duration:>60000000000) as long_flows'
          }
        }
      },
      {
        h: 3,
        w: 8,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: '协议流量趋势图',
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'flowTrend',
          dataSource: 1,
          displayMaps: {
            type: 'multiple',
            key: 'network.transport',
            value: 'networkbytes',
            tooltipField: 'network.transport'
          },
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (_time:${_time},network.transport) sum(network.bytes) as networkbytes | math networkbytes / 1024 / 1024 as networkbytes'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 2,
        i: uuidv4(),
        name: t('log.analysis.packetbeat.transportDistribution'),
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'flowDonut',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: 'network.transport',
            value: 'flowcount',
            tooltipField: 'network.transport'
          },
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (network.transport) count() as flowcount | sort by (flowcount desc)'
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: '源 IP 流量 Top 10',
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'flowBar',
          dataSource: 1,
          barColor: '#155AEF',
          displayMaps: {
            type: 'single',
            key: 'source.ip',
            value: 'src_bytes',
            tooltipField: 'source.ip'
          },
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (source.ip) sum(network.bytes) as src_bytes | math src_bytes / 1024 / 1024 as src_bytes | sort by (src_bytes desc) | limit 10'
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 6,
        y: 5,
        i: uuidv4(),
        name: '目标端口流量 Top 10',
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'flowBar',
          dataSource: 1,
          barColor: '#15B77E',
          displayMaps: {
            type: 'single',
            key: 'destination.port',
            value: 'dst_bytes',
            tooltipField: 'destination.port'
          },
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (destination.port) sum(network.bytes) as dst_bytes | math dst_bytes / 1024 / 1024 as dst_bytes | sort by (dst_bytes desc) | limit 10'
          }
        }
      },
      {
        h: 5,
        w: 12,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: t('log.analysis.packetbeat.highTrafficSankey'),
        moved: false,
        static: false,
        description:
          '展示高流量五元组关系，帮助定位源、目标、协议与端口之间的流量链路。',
        valueConfig: {
          chartType: 'flowSankey',
          dataSource: 1,
          displayMaps: {
            sourceField: 'source.ip',
            targetField: 'destination.ip',
            valueField: 'flow_bytes',
            middleField: 'network.transport',
            tooltipFields: {
              flow_bytes: t('log.analysis.packetbeat.networkTrafficMB'),
              'source.ip': t('log.analysis.packetbeat.sourceIP'),
              'destination.ip': t('log.analysis.packetbeat.destinationIP'),
              'network.transport': t('log.analysis.packetbeat.transport'),
              'source.port': t('log.analysis.packetbeat.sourcePort'),
              'destination.port': t('log.analysis.packetbeat.destinationPort')
            }
          },
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (source.ip,destination.ip,network.transport,source.port,destination.port) sum(network.bytes) as flow_bytes | math flow_bytes / 1024 / 1024 as flow_bytes | sort by (flow_bytes desc) | limit 20'
          }
        }
      },
      {
        h: 4,
        w: 12,
        x: 0,
        y: 13,
        i: uuidv4(),
        name: t('log.analysis.packetbeat.topFlowSessions'),
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'flowTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            {
              title: t('log.analysis.packetbeat.sourceIP'),
              dataIndex: 'source.ip',
              key: 'source.ip'
            },
            {
              title: t('log.analysis.packetbeat.destinationIP'),
              dataIndex: 'destination.ip',
              key: 'destination.ip'
            },
            {
              title: t('log.analysis.packetbeat.transport'),
              dataIndex: 'network.transport',
              key: 'network.transport'
            },
            {
              title: t('log.analysis.packetbeat.destinationPort'),
              dataIndex: 'destination.port',
              key: 'destination.port'
            },
            {
              title: t('log.analysis.packetbeat.networkTrafficMB'),
              dataIndex: 'flow_bytes',
              key: 'flow_bytes',
              render: (val: string) => formatNumericValue(val)
            },
            {
              title: t('log.analysis.packetbeat.flowDurationSec'),
              dataIndex: 'duration_sec',
              key: 'duration_sec',
              render: (val: string) => formatNumericValue(val)
            }
          ],
          dataSourceParams: {
            query:
              'collect_type:"flows" | stats by (source.ip,destination.ip,network.transport,destination.port) sum(network.bytes) as flow_bytes, max(event.duration) as duration_ns | math flow_bytes / 1024 / 1024 as flow_bytes | math duration_ns / 1000000000 as duration_sec | sort by (flow_bytes desc) | limit 20'
          }
        }
      }
    ]
  };
};
