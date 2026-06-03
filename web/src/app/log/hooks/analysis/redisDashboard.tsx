import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';

const REDIS_BASE = 'collect_type:"redis" event.dataset:"redis.log"';

export const useRedisDashboard = () => {
  const { t } = useTranslation();

  return {
    name: t('log.analysis.redis.dashboardName'),
    desc: '',
    id: '8',
    category: 'middleware',
    categoryName: t('log.analysis.category.middleware'),
    collectTypeName: 'redis',
    filters: {},
    other: {},
    view_sets: [
      {
        h: 2,
        w: 3,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.redis.totalLogCount'),
        description: t('log.analysis.redis.totalLogCountDesc'),
        valueConfig: {
          chartType: 'redisKpiCard',
          dataSource: 1,
          displayMaps: { type: 'single', key: '_time', value: 'total_count' },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE}`,
            query: `${REDIS_BASE} | stats by (_time:\${_time}) count() as total_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 3,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.redis.errCount'),
        description: t('log.analysis.redis.errCountDesc'),
        valueConfig: {
          chartType: 'redisKpiCard',
          dataSource: 1,
          color: '#EF4444',
          displayMaps: { type: 'single', key: '_time', value: 'err_count' },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE} _msg:"ERR "`,
            query: `${REDIS_BASE} | stats by (_time:\${_time}) count() if (_msg:"ERR ") as err_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.redis.typeClusterErrors'),
        description: t('log.analysis.redis.typeClusterErrorsDesc'),
        valueConfig: {
          chartType: 'redisKpiCard',
          dataSource: 1,
          color: '#F97316',
          displayMaps: { type: 'single', key: '_time', value: 'type_err_count' },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE} (_msg:"WRONGTYPE " OR _msg:"CLUSTERDOWN ")`,
            query: `${REDIS_BASE} | stats by (_time:\${_time}) count() if (_msg:"WRONGTYPE " OR _msg:"CLUSTERDOWN ") as type_err_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.redis.authFailures'),
        description: t('log.analysis.redis.authFailuresDesc'),
        valueConfig: {
          chartType: 'redisKpiCard',
          dataSource: 1,
          color: '#8B5CF6',
          displayMaps: { type: 'single', key: '_time', value: 'auth_err_count' },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE} (_msg:"WRONGPASS " OR _msg:"NOAUTH " OR _msg:"AUTH failed")`,
            query: `${REDIS_BASE} | stats by (_time:\${_time}) count() if (_msg:"WRONGPASS " OR _msg:"NOAUTH " OR _msg:"AUTH failed") as auth_err_count`
          }
        }
      },
      {
        h: 3,
        w: 8,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: t('log.analysis.redis.logTrend'),
        description: t('log.analysis.redis.logTrendDesc'),
        valueConfig: {
          chartType: 'redisTrendLine',
          dataSource: 1,
          displayMaps: {
            key: '_time',
            totalField: 'total_count',
            errField: 'err_count',
            totalLabel: t('log.analysis.redis.totalLogSeries'),
            errLabel: t('log.analysis.redis.errSeries')
          },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE}`,
            query: `${REDIS_BASE} | stats by (_time:\${_time}) count() as total_count, count() if (_msg:"ERR ") as err_count`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 2,
        i: uuidv4(),
        name: t('log.analysis.redis.eventTypeDistribution'),
        description: t('log.analysis.redis.eventTypeDistributionDesc'),
        valueConfig: {
          chartType: 'redisDonut',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: `${REDIS_BASE}`,
            query: `${REDIS_BASE} | stats count() as total_count, count() if (_msg:"ERR ") as err_count, count() if (_msg:"WRONGTYPE " OR _msg:"CLUSTERDOWN ") as type_err_count, count() if (_msg:"WRONGPASS " OR _msg:"NOAUTH " OR _msg:"AUTH failed") as auth_err_count, count() if (_msg:"command: ") as cmd_count`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: t('log.analysis.redis.topErrorCases'),
        description: t('log.analysis.redis.topErrorCasesDesc'),
        valueConfig: {
          chartType: 'redisInstanceBar',
          dataSource: 1,
          displayMaps: { key: 'err_case', value: 'case_count' },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE} _msg:"case="`,
            query: `${REDIS_BASE} _msg:"case=" | extract "case=<err_case>" from _msg | stats by (err_case) count() as case_count | sort by (case_count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: 'Top 异常节点',
        valueConfig: {
          chartType: 'redisInstanceBar',
          dataSource: 1,
          displayMaps: { key: 'node_ip', value: 'err_count' },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE} _msg:"ERR " node_ip:*`,
            query: `${REDIS_BASE} _msg:"ERR " node_ip:* | stats by (node_ip) count() as err_count | sort by (err_count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 5,
        i: uuidv4(),
        name: 'Top 认证失败节点',
        valueConfig: {
          chartType: 'redisInstanceBar',
          dataSource: 1,
          displayMaps: { key: 'node_ip', value: 'auth_err_count' },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE} (_msg:"WRONGPASS " OR _msg:"NOAUTH " OR _msg:"AUTH failed") node_ip:*`,
            query: `${REDIS_BASE} node_ip:* | stats by (node_ip) count() if (_msg:"WRONGPASS " OR _msg:"NOAUTH " OR _msg:"AUTH failed") as auth_err_count | sort by (auth_err_count desc) | limit 10`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: '最近错误日志',
        description: t('log.analysis.redis.recentLogsDesc'),
        valueConfig: {
          chartType: 'redisLogTable',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: `${REDIS_BASE} _msg:"ERR "`,
            query: `${REDIS_BASE} _msg:"ERR " | sort by (_time desc) | limit 30`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 6,
        y: 8,
        i: uuidv4(),
        name: '最近认证失败日志',
        description: t('log.analysis.redis.recentLogsDesc'),
        valueConfig: {
          chartType: 'redisLogTable',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: `${REDIS_BASE} (_msg:"WRONGPASS " OR _msg:"NOAUTH " OR _msg:"AUTH failed")`,
            query: `${REDIS_BASE} (_msg:"WRONGPASS " OR _msg:"NOAUTH " OR _msg:"AUTH failed") | sort by (_time desc) | limit 30`
          }
        }
      }
    ]
  };
};
