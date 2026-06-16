import dayjs from 'dayjs';

export interface OperationLogFilterState {
  username?: string;
  app?: string;
  actionType?: string;
}

/**
 * 构建操作日志列表查询参数。
 *
 * 时间范围参数名必须与后端 OperationLogFilter 契约一致
 * (operation_time_start / operation_time_end),否则 django-filter 会静默忽略。
 */
export function buildOperationLogParams(
  filters: OperationLogFilterState,
  timeRange: number[],
  page: number,
  pageSize: number
): Record<string, any> {
  const params: Record<string, any> = {
    page,
    page_size: pageSize,
  };

  if (filters.username) {
    params.username = filters.username;
  }
  if (filters.app) {
    params.app = filters.app;
  }
  if (filters.actionType) {
    params.action_type = filters.actionType;
  }
  if (timeRange && timeRange.length === 2) {
    params.operation_time_start = dayjs(timeRange[0]).format('YYYY-MM-DD HH:mm:ss');
    params.operation_time_end = dayjs(timeRange[1]).format('YYYY-MM-DD HH:mm:ss');
  }
  return params;
}
