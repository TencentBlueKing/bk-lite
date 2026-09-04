/** Oracle 表空间 / 资源 TopN */
export const ORACLE_TOP_N = 8;

interface GuideItem {
  label: string;
  detail: string;
}

export interface OracleTopQuery {
  key: string;
  title: string;
  unit: string;
  color: string;
  query: string;
  labelKeys: string[];
  guide: GuideItem[];
}

export const ORACLE_TOP_QUERIES: OracleTopQuery[] = [
  {
    key: 'tablespace',
    title: '表空间使用率 Top',
    unit: 'percent',
    color: '#EF4444',
    labelKeys: ['tablespace'],
    query: `topk(${ORACLE_TOP_N}, max by (tablespace) (oracledb_tablespace_used_percent_gauge{__$labels__}))`,
    guide: [{ label: '表空间排行', detail: '按使用率最高的表空间排序，定位最需扩容或清理的空间。' }]
  },
  {
    key: 'resource',
    title: '资源限制使用率 Top',
    unit: 'percent',
    color: '#F59E0B',
    labelKeys: ['resource_name'],
    query: `topk(${ORACLE_TOP_N}, clamp_min(oracledb_resource_current_utilization_gauge{__$labels__} / clamp_min(oracledb_resource_limit_value_gauge{__$labels__}, 1) * 100, 0))`,
    guide: [{ label: '资源排行', detail: '按资源限制使用率排序（sessions/processes/memory 等），定位触及上限的资源。' }]
  }
];
