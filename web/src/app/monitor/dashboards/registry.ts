import MysqlDashboard from './mysql';
import RedisDashboard from './redis';
import { ProfessionalDashboardRegistryItem } from './types';
import { normalizeDashboardKey } from './utils';

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
  }
];

export const PROFESSIONAL_DASHBOARD_MAP = new Map(
  PROFESSIONAL_DASHBOARDS.flatMap((item) => {
    const keys = [item.key, item.objectName, item.objectDisplayName].filter(Boolean).map((key) => normalizeDashboardKey(key));
    return keys.map((key) => [key, item.component] as const);
  })
);

export const getProfessionalDashboardKey = (objectName?: string | null, objectDisplayName?: string | null) => {
  const matched = PROFESSIONAL_DASHBOARDS.find((item) => {
    const candidates = [item.key, item.objectName, item.objectDisplayName].map((value) => normalizeDashboardKey(value));
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
    const dashboardPath = `/monitor/view/dashboard/${item.key}`;
    return normalizedUrl === dashboardPath || normalizedUrl.startsWith(`${dashboardPath}/`);
  });
  return matched?.inheritedPermissionPath || '';
};
