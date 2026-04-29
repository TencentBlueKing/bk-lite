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
      {
        h: 3,
        w: 9,
        x: 0,
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
      {
        h: 3,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.docker.totalLogCount'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.totalLogCountDesc'),
        valueConfig: {
          chartType: 'single',
          dataSource: 1,
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
        w: 9,
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
        w: 3,
        x: 9,
        y: 3,
        i: uuidv4(),
        name: t('log.analysis.docker.errorLogCount'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.errorLogCountDesc'),
        valueConfig: {
          chartType: 'single',
          dataSource: 1,
          color: 'var(--color-fail)',
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
        x: 0,
        y: 6,
        i: uuidv4(),
        name: t('log.analysis.docker.containerDistribution'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.containerDistributionDesc'),
        valueConfig: {
          chartType: 'pie',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: 'container_name',
            value: 'logcount',
            tooltipField: 'container_name'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" | stats by (container_name) count() as logcount | sort by (logcount desc)'
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 6,
        y: 6,
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
      {
        h: 4,
        w: 6,
        x: 0,
        y: 9,
        i: uuidv4(),
        name: t('log.analysis.docker.topContainers'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.topContainersDesc'),
        valueConfig: {
          chartType: 'table',
          dataSource: 1,
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
        h: 4,
        w: 6,
        x: 6,
        y: 9,
        i: uuidv4(),
        name: t('log.analysis.docker.topImages'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.topImagesDesc'),
        valueConfig: {
          chartType: 'table',
          dataSource: 1,
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
        h: 4,
        w: 12,
        x: 0,
        y: 13,
        i: uuidv4(),
        name: t('log.analysis.docker.topHosts'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.topHostsDesc'),
        valueConfig: {
          chartType: 'table',
          dataSource: 1,
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
