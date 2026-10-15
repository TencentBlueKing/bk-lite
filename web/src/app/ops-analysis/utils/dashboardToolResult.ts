import type { DashboardProposal } from '@/app/ops-analysis/utils/applyDashboardProposal';

export const DASHBOARD_APPLY_TOOL = 'prepare_dashboard_proposal';
export const DASHBOARD_APPLY_ACTION = 'dashboard_config_apply';

export interface DashboardApplyAction {
  dashboardId: unknown;
  proposal: DashboardProposal;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

const readProposal = (value: unknown): DashboardProposal | null => {
  if (typeof value === 'string') {
    try {
      return readProposal(JSON.parse(value));
    } catch {
      return null;
    }
  }
  return isRecord(value) ? (value as DashboardProposal) : null;
};

/** Read a page apply action from a raw tool result. Other payloads are ignored. */
export const readDashboardApplyAction = (content: string): DashboardApplyAction | null => {
  let parsed: unknown;
  try {
    parsed = JSON.parse(content);
  } catch {
    return null;
  }
  if (!isRecord(parsed)) return null;
  const payload = isRecord(parsed.data) ? parsed.data : parsed;
  const pageAction = payload.pageAction;
  if (!isRecord(pageAction) || pageAction.name !== DASHBOARD_APPLY_ACTION) return null;
  const value = pageAction.value;
  if (!isRecord(value)) return null;
  const proposal = readProposal(value.proposal);
  if (!proposal) return null;
  return {
    dashboardId: value.dashboardId,
    proposal,
  };
};

/** First delivery of a tool call id wins. Later copies of the same id are ignored. */
export const claimToolCall = (seen: Set<string>, toolCallId: string) => {
  if (!toolCallId || seen.has(toolCallId)) return false;
  seen.add(toolCallId);
  return true;
};
