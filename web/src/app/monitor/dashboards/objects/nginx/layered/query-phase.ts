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
  sitesKpi: ['starWindowRequests', 'starWindowStatus', 'starTime', 'serverFresh'],
  sitesStatus: ['starStatusStep', 'starWindowStatus'],
  sitesTraffic: ['starBytes', 'serverFresh'],
  sitesTime: ['starTime', 'serverFresh'],
  sitesRank: ['zoneRequestRate', 'zoneWindowRequests', 'serverFresh'],
  sitesTable: ['zoneRequestRate', 'zoneWindowRequests', 'zoneWindowStatus', 'zoneWindowBytes', 'zoneTime', 'starWindowRequests', 'starWindowStatus', 'starWindowBytes', 'starTime', 'serverFresh'],
  filterTable: ['filterRequestRate', 'filterWindowRequests', 'filterWindowStatus', 'filterWindowBytes', 'filterTime', 'filterFresh'],
  upstreamKpi: ['upRequestSum', 'upWindowRequests', 'upWindow5xx', 'upResponseTime', 'upFlags', 'upstreamFresh'],
  upstreamTrend: ['upRequestSum', 'upstreamFresh'],
  upstreamStatus: ['upStatusStep'],
  upstreamTime: ['upResponseTime', 'upRequestTime', 'upstreamFresh'],
  upstreamTable: ['upRequestRate', 'upMemberWindowRequests', 'upMemberWindowStatus', 'upMemberWindowBytes', 'upGroupWindowRequests', 'upGroupWindowStatus', 'upGroupWindowBytes', 'upRequestTime', 'upResponseTime', 'upFlags', 'upstreamFresh']
} as const;
