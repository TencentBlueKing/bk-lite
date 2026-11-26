export type NginxQueryPhase = 'loading' | 'error' | 'ready';

export const phaseOf = (
  keys: readonly string[],
  phases: Readonly<Record<string, NginxQueryPhase>>
): NginxQueryPhase => {
  const list = keys.map((key) => phases[key] ?? 'loading');
  if (list.some((item) => item === 'loading')) return 'loading';
  if (list.some((item) => item === 'error')) return 'error';
  return 'ready';
};

export const NGINX_CARD_QUERIES = {
  collection: ['stubFresh'],
  request: ['requestsRate', 'stubFresh'],
  active: ['conn', 'stubFresh'],
  accept: ['acceptsRate', 'handledRate', 'stubFresh'],
  connections: ['conn', 'stubFresh'],
  dropped: ['acceptsRate', 'handledRate', 'stubFresh'],
  droppedCount: ['droppedWindow', 'stubFresh'],
  sitesKpi: ['starWindowRequests', 'starWindowStatus', 'starTime', 'serverFresh'],
  sitesStatus: ['starStatusStep', 'starWindowStatus'],
  sitesTraffic: ['starBytes', 'serverFresh'],
  sitesTime: ['starTime', 'serverFresh'],
  sitesRank: ['zoneRequestRate', 'zoneWindowRequests', 'serverFresh'],
  sitesTable: ['zoneRequestRate', 'zoneWindowRequests', 'zoneWindowStatus', 'zoneWindowBytes', 'zoneTime', 'starWindowRequests', 'starWindowStatus', 'starWindowBytes', 'starTime', 'serverFresh'],
  filterTable: ['filterRequestRate', 'filterWindowRequests', 'filterWindowStatus', 'filterWindowBytes', 'filterTime', 'filterFresh'],
  upstreamKpi: ['upRequestSum', 'upWindowRequests', 'upWindow5xx', 'upResponseTime', 'upFlags', 'upstreamFresh'],
  upstreamTrend: ['upRequestSum', 'upstreamFresh'],
  upstreamStatus: ['upStatusStep', 'upWindowStatus'],
  upstreamTime: ['upResponseTime', 'upRequestTime', 'upstreamFresh'],
  upstreamTable: ['upRequestRate', 'upMemberWindowRequests', 'upMemberWindowStatus', 'upMemberWindowBytes', 'upGroupWindowRequests', 'upGroupWindowStatus', 'upGroupWindowBytes', 'upRequestTime', 'upResponseTime', 'upFlags', 'upstreamFresh']
} as const;

/** 概览第三张焦点卡用的查询。VTS 探测失败时把探测键算进去，卡面走加载失败而不是当成 stub。 */
export const focusCardQueries = (tab: 'sites' | 'upstream' | 'connections'): readonly string[] => {
  if (tab === 'connections') return NGINX_CARD_QUERIES.active;
  if (tab === 'upstream') return [...NGINX_CARD_QUERIES.upstreamKpi, 'upstreamCap'];
  return [...NGINX_CARD_QUERIES.sitesKpi, 'serverCap'];
};
