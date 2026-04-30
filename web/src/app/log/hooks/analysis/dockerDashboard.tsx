import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';

export const useDockerDashboard = () => {
  const { t } = useTranslation();

  return {
    name: t('log.analysis.docker.dashboardName'),
    desc: '',
    id: '6',
    category: 'container',
    categoryName: t('log.analysis.category.container'),
    collectTypeName: 'docker',
    filters: {},
    other: {},
    view_sets: [
      // Row 0-2: 概览 KPI + 总量趋势
      {
        h: 3,
        w: 3,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.docker.totalLogCount'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.totalLogCountDesc'),
        valueConfig: {
          chartType: 'single',
          dataSource: 1,
          metricLabel: t('log.analysis.docker.totalLogCount'),
          helperText: t('log.analysis.docker.totalLogCountDesc'),
          displayMaps: {
            type: 'single',
            key: 'logcount',
            value: 'logcount',
            tooltipField: 'logcount'
          },
          dataSourceParams: {
            query: 'collect_type:"docker" | stats count() as logcount'
          }
        }
      },
      {
        h: 3,
        w: 3,
        x: 3,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.docker.errorLogCount'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.errorLogCountDesc'),
        valueConfig: {
          chartType: 'single',
          dataSource: 1,
          color: 'var(--color-fail)',
          metricLabel: t('log.analysis.docker.errorLogCount'),
          helperText: t('log.analysis.docker.errorLogCountDesc'),
          displayMaps: {
            type: 'single',
            key: 'errcount',
            value: 'errcount',
            tooltipField: 'errcount'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" stream:"stderr" | stats count() as errcount'
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.docker.logVolumeTrend'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.logVolumeTrendDesc'),
        valueConfig: {
          chartType: 'line',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: 'logcount',
            value: 'logcount',
            tooltipField: 'logcount'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" | stats by (_time:${_time}) count() as logcount'
          }
        }
      },
      // Row 3-5: 错误趋势 + 日志流分布
      {
        h: 3,
        w: 8,
        x: 0,
        y: 3,
        i: uuidv4(),
        name: t('log.analysis.docker.errorLogTrend'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.errorLogTrendDesc'),
        valueConfig: {
          chartType: 'line',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: 'errcount',
            value: 'errcount',
            tooltipField: 'errcount'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" stream:"stderr" | stats by (_time:${_time}) count() as errcount'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 3,
        i: uuidv4(),
        name: t('log.analysis.docker.streamDistribution'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.streamDistributionDesc'),
        valueConfig: {
          chartType: 'pie',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: 'stream',
            value: 'logcount',
            tooltipField: 'stream'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" | stats by (stream) count() as logcount | sort by (logcount desc)'
          }
        }
      },
      // Row 6-9: 深度分析 — 热力图 + 构成趋势并排
      {
        h: 4,
        w: 6,
        x: 0,
        y: 6,
        i: uuidv4(),
        name: t('log.analysis.docker.errorHeatmap'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.errorHeatmapDesc'),
        valueConfig: {
          chartType: 'heatmap',
          dataSource: 1,
          limit: 8,
          displayMaps: {
            time: '_time',
            category: 'container_name',
            value: 'errcount'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" stream:"stderr" | stats by (_time:${_time},container_name) count() as errcount | sort by (errcount desc)'
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 6,
        y: 6,
        i: uuidv4(),
        name: t('log.analysis.docker.containerVolumeStackLineCompare'),
        moved: false,
        static: false,
        description: t(
          'log.analysis.docker.containerVolumeStackLineCompareDesc'
        ),
        valueConfig: {
          chartType: 'line',
          dataSource: 1,
          displayMaps: {
            type: 'multiple',
            key: 'container_name',
            value: 'logcount',
            tooltipField: 'logcount',
            stack: 'total'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" | stats by (_time:${_time},container_name) count() as logcount | sort by (logcount desc)'
          }
        }
      },
      // Row 10-12: Top 排行三栏并排
      {
        h: 3,
        w: 4,
        x: 0,
        y: 10,
        i: uuidv4(),
        name: t('log.analysis.docker.topContainers'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.topContainersDesc'),
        valueConfig: {
          chartType: 'table',
          dataSource: 1,
          showIndex: true,
          columns: [
            {
              title: t('log.analysis.docker.containerName'),
              dataIndex: 'container_name',
              key: 'container_name'
            },
            {
              title: t('log.analysis.docker.logCount'),
              dataIndex: 'logcount',
              key: 'logcount'
            }
          ],
          dataSourceParams: {
            query:
              'collect_type:"docker" | stats by (container_name) count() as logcount | sort by (logcount desc) | limit 20'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 4,
        y: 10,
        i: uuidv4(),
        name: t('log.analysis.docker.topImages'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.topImagesDesc'),
        valueConfig: {
          chartType: 'table',
          dataSource: 1,
          showIndex: true,
          columns: [
            {
              title: t('log.analysis.docker.imageName'),
              dataIndex: 'image',
              key: 'image'
            },
            {
              title: t('log.analysis.docker.logCount'),
              dataIndex: 'logcount',
              key: 'logcount'
            }
          ],
          dataSourceParams: {
            query:
              'collect_type:"docker" | stats by (image) count() as logcount | sort by (logcount desc) | limit 20'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 10,
        i: uuidv4(),
        name: t('log.analysis.docker.topHosts'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.topHostsDesc'),
        valueConfig: {
          chartType: 'table',
          dataSource: 1,
          showIndex: true,
          columns: [
            {
              title: t('log.analysis.docker.hostName'),
              dataIndex: 'host',
              key: 'host'
            },
            {
              title: t('log.analysis.docker.logCount'),
              dataIndex: 'logcount',
              key: 'logcount'
            }
          ],
          dataSourceParams: {
            query:
              'collect_type:"docker" | stats by (host) count() as logcount | sort by (logcount desc) | limit 20'
          }
        }
      }
    ]
  };
};
