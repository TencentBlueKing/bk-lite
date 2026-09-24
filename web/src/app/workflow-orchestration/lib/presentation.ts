import type { ExecutionStatus, WorkflowStatus } from './types';

export const workflowStatusPresentation: Record<WorkflowStatus, { label: string; color: string }> = {
  DRAFT: { label: '草稿', color: 'default' },
  PUBLISHED: { label: '已发布', color: 'success' },
};

export const executionStatusPresentation: Record<ExecutionStatus, { label: string; color: string }> = {
  QUEUED: { label: '排队中', color: 'default' },
  RUNNING: { label: '执行中', color: 'processing' },
  WAITING_APPROVAL: { label: '等待审批', color: 'warning' },
  TERMINATING: { label: '终止中', color: 'warning' },
  SUCCEEDED: { label: '成功', color: 'success' },
  FAILED: { label: '失败', color: 'error' },
  TIMED_OUT: { label: '已超时', color: 'error' },
  TERMINATED: { label: '已终止', color: 'warning' },
};

const NODE_STATE_LABELS: Record<string, string> = {
  ACTIONABLE: '待我处理',
  FAILED: '失败',
  TIMED_OUT: '已超时',
  RUNNING: '运行中',
  WAITING: '等待审批',
  WARNING: '有告警',
  SUCCESS: '成功',
  SKIPPED: '已跳过',
  UNREACHABLE: '未到达',
  PENDING: '未开始',
};

const TRIGGER_TYPE_LABELS: Record<string, { id: string; defaultMessage: string }> = {
  FORM: { id: 'workflowOrchestration.trigger.form', defaultMessage: '表单' },
  SCHEDULE: { id: 'workflowOrchestration.trigger.schedule', defaultMessage: '定时' },
  WEBHOOK: { id: 'workflowOrchestration.trigger.webhook', defaultMessage: 'Webhook' },
  NATS: { id: 'workflowOrchestration.trigger.nats', defaultMessage: 'NATS' },
};

const SYSTEM_STARTED_BY: Record<string, { id: string; defaultMessage: string }> = {
  'workflow-scheduler': { id: 'workflowOrchestration.execution.startedBySystem.scheduler', defaultMessage: '定时调度' },
  'mvp-verifier': { id: 'workflowOrchestration.execution.startedBySystem.mvpVerifier', defaultMessage: 'MVP 验收' },
  openapi: { id: 'workflowOrchestration.execution.startedBySystem.openapi', defaultMessage: 'OpenAPI' },
};

const EXECUTION_INFO_LABELS: Record<string, { id: string; defaultMessage: string }> = {
  status: { id: 'common.status', defaultMessage: '状态' },
  trigger_type: { id: 'workflowOrchestration.trigger.title', defaultMessage: '触发器' },
  started_by: { id: 'workflowOrchestration.execution.startedBy', defaultMessage: '发起人' },
  started_at: { id: 'workflowOrchestration.execution.startedAt', defaultMessage: '开始时间' },
  finished_at: { id: 'workflowOrchestration.execution.finishedAt', defaultMessage: '结束时间' },
  duration_ms: { id: 'workflowOrchestration.execution.duration', defaultMessage: '耗时' },
  retry_count: { id: 'workflowOrchestration.node.retryCount', defaultMessage: '重试次数' },
};

type Translate = (id: string, defaultMessage?: string, values?: Record<string, unknown>) => string;

/** Format execution duration; long spans use job-record style `Xh Ym`. */
export const formatDuration = (durationMs: number | null | undefined) => {
  if (durationMs == null || durationMs < 0 || Number.isNaN(durationMs)) return '--';
  if (durationMs < 1000) return `${durationMs} ms`;
  const totalSeconds = Math.floor(durationMs / 1000);
  if (totalSeconds < 60) return `${(durationMs / 1000).toFixed(1)} s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainMinutes = minutes % 60;
  return `${hours}h ${remainMinutes}m`;
};

export const formatBytes = (size: number) => size < 1024 * 1024 ? `${(size / 1024).toFixed(1)} KiB` : `${(size / 1024 / 1024).toFixed(1)} MiB`;
export const formatJson = (value: unknown) => JSON.stringify(value ?? {}, null, 2);

const ISO_LIKE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

/** Format scalar execution-info values; localize ISO timestamps for display. */
export function formatExecutionInfoValue(
  value: unknown,
  convertToLocalizedTime: (iso: string, format?: string) => string,
): string {
  if (value == null || value === '') return '--';
  if (typeof value === 'object') return formatJson(value);
  if (typeof value === 'string' && ISO_LIKE.test(value)) {
    return convertToLocalizedTime(value) || value;
  }
  return String(value);
}

export function formatTriggerTypeLabel(value: string | null | undefined, t: Translate): string {
  if (!value) return '--';
  const mapped = TRIGGER_TYPE_LABELS[value];
  return mapped ? t(mapped.id, mapped.defaultMessage) : value;
}

export function formatStartedBy(value: string | null | undefined, t: Translate): string {
  if (!value) return '--';
  const mapped = SYSTEM_STARTED_BY[value];
  return mapped ? t(mapped.id, mapped.defaultMessage) : value;
}

export function formatExecutionInfoLabel(key: string, t: Translate): string {
  const mapped = EXECUTION_INFO_LABELS[key];
  return mapped ? t(mapped.id, mapped.defaultMessage) : key;
}

function formatLifecycleStatusValue(value: string, t: Translate): string {
  if (Object.hasOwn(executionStatusPresentation, value)) {
    const status = value as ExecutionStatus;
    return t(`workflowOrchestration.execution.status.${status}`, executionStatusPresentation[status].label);
  }
  if (Object.hasOwn(NODE_STATE_LABELS, value)) {
    return t(`workflowOrchestration.node.state.${value}`, NODE_STATE_LABELS[value]);
  }
  return value;
}

export function presentExecutionInfoItem(
  key: string,
  value: unknown,
  t: Translate,
  convertToLocalizedTime: (iso: string, format?: string) => string,
): { label: string; children: string } {
  const label = formatExecutionInfoLabel(key, t);
  if (key === 'status' && typeof value === 'string') {
    return { label, children: formatLifecycleStatusValue(value, t) };
  }
  if (key === 'trigger_type' && typeof value === 'string') {
    return { label, children: formatTriggerTypeLabel(value, t) };
  }
  if (key === 'started_by' && typeof value === 'string') {
    return { label, children: formatStartedBy(value, t) };
  }
  if (key === 'duration_ms') {
    const numeric = typeof value === 'number' ? value : Number(value);
    return { label, children: formatDuration(Number.isFinite(numeric) ? numeric : null) };
  }
  return { label, children: formatExecutionInfoValue(value, convertToLocalizedTime) };
}
