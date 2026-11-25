export const UNRECORDED = 'unrecorded' as const;

export type OperationOutcome = 'success' | 'failure' | 'accepted' | typeof UNRECORDED;

export interface ChangeField {
  key: string;
  before: unknown;
  after: unknown;
}

export type OperationLogChangeView =
  | { kind: 'unrecorded' }
  | { kind: 'hidden' }
  | { kind: 'none' }
  | { kind: 'create'; after: Record<string, unknown> }
  | { kind: 'delete'; before: Record<string, unknown> }
  | { kind: 'update'; fields: ChangeField[] };

export interface OperationLogDetailRow {
  username?: string;
  operation_time?: string;
  source_ip?: string;
  app?: string;
  app_name?: string;
  action_type?: string;
  target_type?: string;
  target_name?: string;
  target_id?: string;
  outcome?: string | null;
  failure_reason?: string | null;
  detail?: Record<string, any> | null;
}

export interface OperationLogDetailView {
  operator: string;
  operationTime: string;
  appName: string;
  sourceIp: string;
  targetType: string;
  targetName: string;
  targetId: string;
  outcome: OperationOutcome;
  failureReason: string;
  showAcceptedHint: boolean;
  changes: OperationLogChangeView;
}

export function hasOperationDetail(row: { detail?: Record<string, any> | null }): boolean {
  return !!row.detail && typeof row.detail === 'object' && Object.keys(row.detail).length > 0;
}

export function recordedOrUnrecorded(value?: string | null): string {
  const text = (value ?? '').trim();
  return text ? text : UNRECORDED;
}

export function normalizeOperationOutcome(outcome?: string | null): OperationOutcome {
  if (outcome === 'success' || outcome === 'failure' || outcome === 'accepted') {
    return outcome;
  }
  return UNRECORDED;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function valuesEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function changedFields(
  before: Record<string, unknown>,
  after: Record<string, unknown>
): ChangeField[] {
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  const fields: ChangeField[] = [];
  keys.forEach((key) => {
    if (!valuesEqual(before[key], after[key])) {
      fields.push({ key, before: before[key], after: after[key] });
    }
  });
  return fields;
}

export function buildOperationLogChangeView(row: OperationLogDetailRow): OperationLogChangeView {
  const outcome = normalizeOperationOutcome(row.outcome);
  if (outcome === UNRECORDED) {
    return { kind: 'unrecorded' };
  }
  if (outcome !== 'success') {
    return { kind: 'hidden' };
  }

  const detail = row.detail && typeof row.detail === 'object' ? row.detail : {};
  const before = detail.before_data;
  const after = detail.after_data;
  const actionType = row.action_type;

  if (actionType === 'create') {
    if (!isPlainObject(after) || Object.keys(after).length === 0) {
      return { kind: 'none' };
    }
    return { kind: 'create', after };
  }

  if (actionType === 'delete') {
    if (!isPlainObject(before) || Object.keys(before).length === 0) {
      return { kind: 'none' };
    }
    return { kind: 'delete', before };
  }

  if (actionType === 'update') {
    if (!isPlainObject(before) || !isPlainObject(after)) {
      return { kind: 'none' };
    }
    const fields = changedFields(before, after);
    return fields.length ? { kind: 'update', fields } : { kind: 'none' };
  }

  return { kind: 'none' };
}

export function buildOperationLogDetailView(row: OperationLogDetailRow): OperationLogDetailView {
  const outcome = normalizeOperationOutcome(row.outcome);
  return {
    operator: recordedOrUnrecorded(row.username),
    operationTime: recordedOrUnrecorded(row.operation_time),
    appName: recordedOrUnrecorded(row.app_name || row.app),
    sourceIp: recordedOrUnrecorded(row.source_ip),
    targetType: recordedOrUnrecorded(row.target_type),
    targetName: recordedOrUnrecorded(row.target_name),
    targetId: recordedOrUnrecorded(row.target_id),
    outcome,
    failureReason: outcome === 'failure' ? (row.failure_reason || '') : '',
    showAcceptedHint: outcome === 'accepted',
    changes: buildOperationLogChangeView(row),
  };
}
