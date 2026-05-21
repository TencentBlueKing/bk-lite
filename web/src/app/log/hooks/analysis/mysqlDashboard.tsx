import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';

const MYSQL_EXTRACT_QUERY_TIME =
  'extract "Query_time: <query_time>  Lock_time:" from _msg';
const MYSQL_EXTRACT_LOCK_TIME =
  'extract "Lock_time: <lock_time> Rows_sent:" from _msg';
const MYSQL_EXTRACT_USER = 'extract "# User@Host: <mysql_user>[" from _msg';

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
      // ─── ROW 1 (y=0, h=2): 4 个 KPI ─────────────────────────────────────────
      {
        h: 2,
        w: 3,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: '慢查询总数',
        moved: false,
        static: false,
        description: '周期内慢查询总条数。',
        valueConfig: {
          chartType: 'mysqlKpiCard',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: '_time',
            value: 'slow_count'
          },
          dataSourceParams: {
            searchQuery: 'collect_type:"mysql" event.dataset:"mysql.slowlog"',
            query:
              'collect_type:"mysql" event.dataset:"mysql.slowlog" | stats by (_time:${_time}) count() as slow_count'
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 3,
        y: 0,
        i: uuidv4(),
        name: '平均查询耗时',
        moved: false,
        static: false,
        description: '周期内慢查询平均执行耗时。',
        valueConfig: {
          chartType: 'mysqlKpiCard',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: '_time',
            value: 'avg_time'
          },
          dataSourceParams: {
            searchQuery: 'collect_type:"mysql" event.dataset:"mysql.slowlog"',
            query: `collect_type:"mysql" event.dataset:"mysql.slowlog" | ${MYSQL_EXTRACT_QUERY_TIME} | stats by (_time:\${_time}) avg(query_time) as avg_time`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: '锁等待查询数',
        moved: false,
        static: false,
        description: '锁等待时间 >0 的慢查询数。',
        valueConfig: {
          chartType: 'mysqlKpiCard',
          dataSource: 1,
          color: '#faad14',
          displayMaps: {
            type: 'single',
            key: '_time',
            value: 'lock_count'
          },
          dataSourceParams: {
            searchQuery:
              'collect_type:"mysql" event.dataset:"mysql.slowlog" _msg:"Lock_time:"',
            query: `collect_type:"mysql" event.dataset:"mysql.slowlog" | ${MYSQL_EXTRACT_LOCK_TIME} | stats by (_time:\${_time}) count() if (lock_time:>0) as lock_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: '错误日志数',
        moved: false,
        static: false,
        description: '周期内 error 日志条数。',
        valueConfig: {
          chartType: 'mysqlKpiCard',
          dataSource: 1,
          color: '#f5222d',
          displayMaps: {
            type: 'single',
            key: '_time',
            value: 'error_count'
          },
          dataSourceParams: {
            searchQuery: 'collect_type:"mysql" event.dataset:"mysql.error"',
            query:
              'collect_type:"mysql" event.dataset:"mysql.error" | stats by (_time:${_time}) count() as error_count'
          }
        }
      },

      // ─── ROW 2 (y=2, h=3): 双轴趋势图 ────────────────────────────────────────
      {
        h: 3,
        w: 6,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: '慢查询数 & 平均耗时趋势',
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'mysqlDualLine',
          dataSource: 1,
          displayMaps: {
            type: 'dual',
            key: '_time',
            value: 'slow_count',
            barField: 'slow_count',
            lineField: 'avg_time',
            barLabel: '慢查询次数',
            lineLabel: '平均耗时(s)'
          },
          dataSourceParams: {
            searchQuery: 'collect_type:"mysql" event.dataset:"mysql.slowlog"',
            query: `collect_type:"mysql" event.dataset:"mysql.slowlog" | ${MYSQL_EXTRACT_QUERY_TIME} | stats by (_time:\${_time}) count() as slow_count, avg(query_time) as avg_time`
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 6,
        y: 2,
        i: uuidv4(),
        name: '锁等待数 & 平均锁时趋势',
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'mysqlDualLine',
          dataSource: 1,
          displayMaps: {
            type: 'dual',
            key: '_time',
            value: 'lock_count',
            barField: 'lock_count',
            lineField: 'avg_lock_time',
            barLabel: '锁等待次数',
            lineLabel: '平均锁时(s)'
          },
          dataSourceParams: {
            searchQuery:
              'collect_type:"mysql" event.dataset:"mysql.slowlog" _msg:"Lock_time:"',
            query: `collect_type:"mysql" event.dataset:"mysql.slowlog" | ${MYSQL_EXTRACT_LOCK_TIME} | stats by (_time:\${_time}) count() if (lock_time:>0) as lock_count, avg(lock_time) as avg_lock_time`
          }
        }
      },

      // ─── ROW 3 (y=5, h=3): 耗时分布 + Top 慢 SQL ────────────────────────────
      {
        h: 3,
        w: 4,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: '查询耗时分布',
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'mysqlDonut',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: 'bucket',
            value: 'cnt'
          },
          dataSourceParams: {
            searchQuery: 'collect_type:"mysql" event.dataset:"mysql.slowlog"',
            query: `collect_type:"mysql" event.dataset:"mysql.slowlog" | ${MYSQL_EXTRACT_QUERY_TIME} | stats count() if (query_time:<0.1) as cnt_lt01, count() if (query_time:>=0.1 query_time:<1) as cnt_01_1, count() if (query_time:>=1 query_time:<10) as cnt_1_10, count() if (query_time:>=10) as cnt_gt10`
          }
        }
      },
      {
        h: 3,
        w: 8,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: 'Top 15 慢 SQL（按平均耗时）',
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'mysqlSlowTable',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: 'collect_type:"mysql" event.dataset:"mysql.slowlog"',
            query: `collect_type:"mysql" event.dataset:"mysql.slowlog" | ${MYSQL_EXTRACT_QUERY_TIME} | stats by (_msg) count() as exec_count, avg(query_time) as avg_time, max(query_time) as max_time | sort by (avg_time desc) | limit 15`
          }
        }
      },

      // ─── ROW 4 (y=8, h=3): 来源维度分析 ─────────────────────────────────────
      {
        h: 3,
        w: 6,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: 'Top 慢查询用户',
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'mysqlInstanceBar',
          dataSource: 1,
          displayMaps: {
            key: 'mysql_user',
            value: 'slow_count'
          },
          dataSourceParams: {
            searchQuery: 'collect_type:"mysql" event.dataset:"mysql.slowlog"',
            query: `collect_type:"mysql" event.dataset:"mysql.slowlog" | ${MYSQL_EXTRACT_USER} | stats by (mysql_user) count() as slow_count | sort by (slow_count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 6,
        y: 8,
        i: uuidv4(),
        name: 'Top 慢查询实例',
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'mysqlInstanceBar',
          dataSource: 1,
          displayMaps: {
            key: 'node_ip',
            value: 'slow_count'
          },
          dataSourceParams: {
            searchQuery: 'collect_type:"mysql" event.dataset:"mysql.slowlog"',
            query:
              'collect_type:"mysql" event.dataset:"mysql.slowlog" node_ip:* | stats by (node_ip) count() as slow_count | sort by (slow_count desc) | limit 10'
          }
        }
      },

      // ─── ROW 5 (y=11, h=4): 原始明细 ─────────────────────────────────────────
      {
        h: 4,
        w: 7,
        x: 0,
        y: 11,
        i: uuidv4(),
        name: '最近慢查询明细',
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'mysqlDetailTable',
          dataSource: 1,
          variant: 'slowlog',
          dataSourceParams: {
            searchQuery: 'collect_type:"mysql" event.dataset:"mysql.slowlog"',
            query:
              'collect_type:"mysql" event.dataset:"mysql.slowlog" | sort by (_time desc) | limit 20'
          }
        }
      },
      {
        h: 4,
        w: 5,
        x: 7,
        y: 11,
        i: uuidv4(),
        name: '最近错误日志',
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'mysqlDetailTable',
          dataSource: 1,
          variant: 'errorlog',
          dataSourceParams: {
            searchQuery: 'collect_type:"mysql" event.dataset:"mysql.error"',
            query:
              'collect_type:"mysql" event.dataset:"mysql.error" | sort by (_time desc) | limit 20'
          }
        }
      }
    ]
  };
};
