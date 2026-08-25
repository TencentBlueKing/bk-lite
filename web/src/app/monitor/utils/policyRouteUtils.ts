export type MonitorStrategyDetailType = 'edit' | 'add' | 'builtIn';

export interface MonitorStrategyDetailParams {
  id?: string | number;
  name?: string;
  monitorObjId: string | number;
  monitorName: string;
}

export function buildMonitorStrategyDetailUrl(
  type: MonitorStrategyDetailType | string,
  params: MonitorStrategyDetailParams
): string {
  const searchParams = new URLSearchParams({
    monitorObjId: String(params.monitorObjId),
    monitorName: params.monitorName,
    type
  });
  if (params.id !== undefined && params.id !== '') {
    searchParams.set('id', String(params.id));
  }
  if (params.name) {
    searchParams.set('name', params.name);
  }
  return `/monitor/event/strategy/detail?${searchParams.toString()}`;
}
