import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';

export const useMysqlDashboard = () => {
  const { t } = useTranslation();

  return {
    name: t('log.analysis.mysql.dashboardName'),
    desc: '',
    id: '7',
    category: 'middleware',
    categoryName: t('log.analysis.category.middleware'),
    collectTypeName: 'mysql',
    filters: {},
    other: {},
    view_sets: [
      {
        h: 2,
        w: 3,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.mysql.totalSlowQueries'),
        moved: false,
        static: false,
        description: '统计慢查询总数，并与上一周期对比。',
        valueConfig: {
          chartType: 'kpiCard',
          dataSource: 1,
          icon: 'log',
          metricLabel: t('log.analysis.mysql.totalSlowQueries'),
          displayMaps: {
            type: 'single',
            key: 'slow_count',
            value: 'slow_count',
            tooltipField: 'slow_count'
          },
          dataSourceParams: {
            query:
              'collect_type:"mysql" event.dataset:"mysql.slowlog" | stats count() as slow_count'
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 3,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.mysql.lockWaitQueries'),
        moved: false,
        static: false,
        description: '统计锁等待查询数，并与上一周期对比。',
        valueConfig: {
          chartType: 'kpiCard',
          dataSource: 1,
          icon: 'clock-circle',
          color: '#155AEF',
          metricLabel: t('log.analysis.mysql.lockWaitQueries'),
          displayMaps: {
            type: 'single',
            key: 'lock_wait_count',
            value: 'lock_wait_count',
            tooltipField: 'lock_wait_count'
          },
          dataSourceParams: {
            query:
              'collect_type:"mysql" event.dataset:"mysql.slowlog" mysql.slowlog.lock_time.sec:>0 | stats count() as lock_wait_count'
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.mysql.errorLogCount'),
        moved: false,
        static: false,
        description: '统计错误日志数，并与上一周期对比。',
        valueConfig: {
          chartType: 'kpiCard',
          dataSource: 1,
          icon: 'warning',
          color: '#faad14',
          metricLabel: t('log.analysis.mysql.errorLogCount'),
          displayMaps: {
            type: 'single',
            key: 'error_count',
            value: 'error_count',
            tooltipField: 'error_count'
          },
          dataSourceParams: {
            query:
              'collect_type:"mysql" event.dataset:"mysql.error" | stats count() as error_count'
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: '扫描查询数',
        moved: false,
        static: false,
        description: '统计扫描查询数，并与上一周期对比。',
        valueConfig: {
          chartType: 'kpiCard',
          dataSource: 1,
          icon: 'error',
          color: '#f5222d',
          metricLabel: '扫描查询数',
          displayMaps: {
            type: 'single',
            key: 'scan_count',
            value: 'scan_count',
            tooltipField: 'scan_count'
          },
          dataSourceParams: {
            query:
              'collect_type:"mysql" event.dataset:"mysql.slowlog" mysql.slowlog.rows_examined:>0 | stats count() as scan_count'
          }
        }
      },
      {
        h: 3,
        w: 8,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: t('log.analysis.mysql.slowQueryTrend'),
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'barLine',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: '_time',
            value: 'slow_count'
          },
          dataSourceParams: {
            query:
              'collect_type:"mysql" event.dataset:"mysql.slowlog" | stats by (_time:${_time}) count() as slow_count'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 2,
        i: uuidv4(),
        name: '错误日志趋势',
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'barLine',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: '_time',
            value: 'error_count'
          },
          dataSourceParams: {
            query:
              'collect_type:"mysql" event.dataset:"mysql.error" | stats by (_time:${_time}) count() as error_count'
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: t('log.analysis.mysql.topSlowSql'),
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'table',
          dataSource: 1,
          showIndex: true,
          columns: [
            {
              title: t('log.analysis.mysql.sqlPreview'),
              dataIndex: '_msg',
              key: '_msg'
            },
            {
              title: t('log.analysis.mysql.queryCount'),
              dataIndex: 'slow_count',
              key: 'slow_count'
            }
          ],
          dataSourceParams: {
            query:
              'collect_type:"mysql" event.dataset:"mysql.slowlog" | stats by (_msg) count() as slow_count | sort by (slow_count desc) | limit 15'
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 6,
        y: 5,
        i: uuidv4(),
        name: 'Top 慢查询主机',
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'bar',
          dataSource: 1,
          direction: 'horizontal',
          displayMaps: {
            type: 'single',
            key: 'mysql.slowlog.host',
            value: 'slow_count',
            tooltipField: 'mysql.slowlog.host'
          },
          dataSourceParams: {
            query:
              'collect_type:"mysql" event.dataset:"mysql.slowlog" mysql.slowlog.host:* | stats by (mysql.slowlog.host) count() as slow_count | sort by (slow_count desc) | limit 10'
          }
        }
      },
      {
        h: 3,
        w: 12,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: t('log.analysis.mysql.slowQueryHeatmap'),
        moved: false,
        static: false,
        description:
          '展示不同主机在各时间段内的慢查询数量热力分布，帮助识别热点主机与高发时段。',
        valueConfig: {
          chartType: 'heatmap',
          dataSource: 1,
          limit: 8,
          displayMaps: {
            time: '_time',
            category: 'mysql.slowlog.host',
            value: 'slow_count'
          },
          dataSourceParams: {
            query:
              'collect_type:"mysql" event.dataset:"mysql.slowlog" mysql.slowlog.host:* | stats by (_time:${_time},mysql.slowlog.host) count() as slow_count | sort by (slow_count desc)'
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 0,
        y: 11,
        i: uuidv4(),
        name: t('log.analysis.mysql.recentSlowQueries'),
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'table',
          dataSource: 1,
          showIndex: true,
          columns: [
            {
              title: t('log.analysis.mysql.timestamp'),
              dataIndex: '_time',
              key: '_time'
            },
            {
              title: t('log.analysis.mysql.dataset'),
              dataIndex: 'event.dataset',
              key: 'event.dataset'
            },
            {
              title: t('log.analysis.mysql.logFilePath'),
              dataIndex: 'log.file.path',
              key: 'log.file.path'
            },
            {
              title: t('log.analysis.mysql.rawMessage'),
              dataIndex: '_msg',
              key: '_msg'
            }
          ],
          dataSourceParams: {
            query:
              'collect_type:"mysql" event.dataset:"mysql.slowlog" | sort by (_time desc) | limit 20'
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 6,
        y: 11,
        i: uuidv4(),
        name: t('log.analysis.mysql.recentErrorLogs'),
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'table',
          dataSource: 1,
          showIndex: true,
          columns: [
            {
              title: t('log.analysis.mysql.timestamp'),
              dataIndex: '_time',
              key: '_time'
            },
            {
              title: t('log.analysis.mysql.dataset'),
              dataIndex: 'event.dataset',
              key: 'event.dataset'
            },
            {
              title: t('log.analysis.mysql.rawMessage'),
              dataIndex: '_msg',
              key: '_msg'
            }
          ],
          dataSourceParams: {
            query:
              'collect_type:"mysql" event.dataset:"mysql.error" | sort by (_time desc) | limit 20'
          }
        }
      }
    ]
  };
};
