import type {
  ExecutionTarget,
  JobRecordDetail,
  JobRecordStatus,
} from '@/app/job/types';

type TargetPayload = Record<string, unknown>;

const asPayload = (value: unknown): TargetPayload => (
  value && typeof value === 'object' ? value as TargetPayload : {}
);

const asString = (value: unknown, fallback = ''): string => (
  typeof value === 'string' || typeof value === 'number' ? String(value) : fallback
);

const asNonEmptyString = (value: unknown, fallback = ''): string => {
  const normalized = asString(value);
  return normalized || fallback;
};

const asNullableString = (value: unknown): string | null => (
  typeof value === 'string' ? value : null
);

const asNullableNumber = (value: unknown): number | null => (
  typeof value === 'number' ? value : null
);

const getTargetIdentity = (target: TargetPayload, index: number): string => {
  const candidate = [
    target.target_key,
    target.node_id,
    target.target_id,
    target.id,
  ].find((value) => value !== null && value !== undefined && value !== '');

  return candidate === undefined
    ? `target-${index}`
    : String(candidate);
};

const asStatus = (value: unknown, fallback: JobRecordStatus): JobRecordStatus => (
  typeof value === 'string' ? value as JobRecordStatus : fallback
);

export const mapExecutionResultsToTargets = (results: unknown[]): ExecutionTarget[] => (
  results.map((value, index) => {
    const result = asPayload(value);
    const identity = getTargetIdentity(result, index);
    const status = asStatus(result.status, 'pending');

    return {
      id: identity,
      target: identity,
      target_key: identity,
      target_name: asNonEmptyString(result.name, asNonEmptyString(result.ip, `Target ${index + 1}`)),
      target_ip: asString(result.ip, '-'),
      status,
      status_display: asString(result.status_display, status),
      stdout: asString(result.stdout),
      stderr: asNonEmptyString(result.stderr, asString(result.error_message)),
      exit_code: asNullableNumber(result.exit_code),
      started_at: asNullableString(result.started_at),
      finished_at: asNullableString(result.finished_at),
      error_message: asString(result.error_message),
    };
  })
);

export const mapTargetListToExecutionTargets = (
  targets: unknown[],
  detail: JobRecordDetail,
): ExecutionTarget[] => (
  targets.map((value, index) => {
    const target = asPayload(value);
    const identity = getTargetIdentity(target, index);

    return {
      id: identity,
      target: identity,
      target_key: identity,
      target_name: asNonEmptyString(target.name, asNonEmptyString(target.ip, `Target ${index + 1}`)),
      target_ip: asNonEmptyString(target.ip, '-'),
      status: detail.status,
      status_display: detail.status_display || detail.status,
      stdout: '',
      stderr: '',
      exit_code: null,
      started_at: detail.started_at || null,
      finished_at: detail.finished_at || null,
      error_message: '',
    };
  })
);

export const normalizeExecutionTargets = (detail: JobRecordDetail): JobRecordDetail => {
  if (detail.execution_targets?.length) {
    return detail;
  }

  if (detail.execution_results?.length) {
    return {
      ...detail,
      execution_targets: mapExecutionResultsToTargets(detail.execution_results),
    };
  }

  if (detail.target_list?.length) {
    return {
      ...detail,
      execution_targets: mapTargetListToExecutionTargets(detail.target_list, detail),
    };
  }

  return detail;
};
