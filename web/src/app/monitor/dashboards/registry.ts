import MysqlDashboard from './objects/mysql';
import MongodbDashboard from './objects/mongodb';
import RedisDashboard from './objects/redis';
import ElasticsearchDashboard from './objects/elasticsearch';
import MssqlDashboard from './objects/mssql';
import NginxDashboard from './objects/nginx';
import PostgresqlDashboard from './objects/postgresql';
import { ProfessionalDashboardRegistryItem } from './shared/types';
import { normalizeDashboardKey } from './shared/utils';

export const PROFESSIONAL_DASHBOARDS: ProfessionalDashboardRegistryItem[] = [
  {
    key: 'mysql',
    objectName: 'Mysql',
    objectDisplayName: 'MySQL',
    inheritedPermissionPath: '/monitor/view',
    component: MysqlDashboard
  },
  {
    key: 'redis',
    objectName: 'Redis',
    objectDisplayName: 'Redis',
    inheritedPermissionPath: '/monitor/view',
    component: RedisDashboard
  },
  {
    key: 'mongodb',
    objectName: 'Mongodb',
    objectDisplayName: 'MongoDB',
    inheritedPermissionPath: '/monitor/view',
    component: MongodbDashboard
  },
  {
    key: 'mssql',
    objectName: 'MSSQL',
    objectDisplayName: 'MSSQL',
    inheritedPermissionPath: '/monitor/view',
    component: MssqlDashboard
  },
  {
    key: 'nginx',
    objectName: 'nginx',
    objectDisplayName: 'Nginx',
    inheritedPermissionPath: '/monitor/view',
    component: NginxDashboard
  },
  {
    key: 'postgres',
    aliases: ['postgresql'],
    objectName: 'Postgres',
    objectDisplayName: 'PostgreSQL',
    inheritedPermissionPath: '/monitor/view',
    component: PostgresqlDashboard
  },
  {
    key: 'elasticsearch',
    objectName: 'ElasticSearch',
    objectDisplayName: 'Elasticsearch',
    inheritedPermissionPath: '/monitor/view',
    component: ElasticsearchDashboard
  }
];

export const PROFESSIONAL_DASHBOARD_MAP = new Map(
  PROFESSIONAL_DASHBOARDS.flatMap((item) => {
    const keys = [item.key, ...(item.aliases || []), item.objectName, item.objectDisplayName]
      .filter(Boolean)
      .map((key) => normalizeDashboardKey(key));
    return keys.map((key) => [key, item.component] as const);
  })
);

const getDashboardCandidates = (item: ProfessionalDashboardRegistryItem) =>
  [item.key, ...(item.aliases || []), item.objectName, item.objectDisplayName]
    .filter(Boolean)
    .map((value) => normalizeDashboardKey(value));

export const getProfessionalDashboardKey = (objectName?: string | null, objectDisplayName?: string | null) => {
  const matched = PROFESSIONAL_DASHBOARDS.find((item) => {
    const candidates = getDashboardCandidates(item);
    const objectCandidates = [objectName, objectDisplayName].map((value) => normalizeDashboardKey(value));
    return objectCandidates.some((candidate) => candidate && candidates.includes(candidate));
  });

  return matched?.key || '';
};

export const getProfessionalDashboardUrl = (
  objectName?: string | null,
  objectDisplayName?: string | null,
  queryString?: string
) => {
  const key = getProfessionalDashboardKey(objectName, objectDisplayName);

  if (!key) {
    return '';
  }

  return `/monitor/view/dashboard/${key}${queryString ? `?${queryString}` : ''}`;
};

export const getProfessionalDashboardPermissionPath = (url?: string | null) => {
  const normalizedUrl = String(url || '').replace(/\/$/, '').toLowerCase();
  const matched = PROFESSIONAL_DASHBOARDS.find((item) => {
    return getDashboardCandidates(item).some((candidate) => {
      const dashboardPath = `/monitor/view/dashboard/${candidate}`;
      return normalizedUrl === dashboardPath || normalizedUrl.startsWith(`${dashboardPath}/`);
    });
  });
  return matched?.inheritedPermissionPath || '';
};
