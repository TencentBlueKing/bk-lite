import { IntegrationMonitoredObject } from '@/app/monitor/types/monitor';

export interface OrderParam {
  id: number;
  sort_order: number;
  [key: string]: any;
}

export interface NodeConfigParam {
  configs?: any;
  collect_type?: string;
  monitor_object_id?: number;
  instances?: Omit<IntegrationMonitoredObject, 'key'>[];
}
