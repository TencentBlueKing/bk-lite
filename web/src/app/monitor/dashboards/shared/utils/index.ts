export * from './constants';
export * from './format';
export * from './search-params';
export * from './chart-data';
export * from './time';
export * from './compare';
export * from './instance';
export * from './metric-series';
export * from './collection-status';
export * from './concurrency';

export const normalizeDashboardKey = (value?: string | null) => String(value || '').trim().toLowerCase();

export const isProfessionalDashboardRoute = (pathname?: string | null) => String(pathname || '').startsWith('/monitor/view/dashboard/');
