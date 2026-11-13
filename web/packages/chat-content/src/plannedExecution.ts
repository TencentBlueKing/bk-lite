import { getOpspilotTranslate } from './translation';

export interface PlannedExecutionStepEvent {
  phase: 'start' | 'end' | string;
  step_index: number;
  total_steps: number;
  objective: string;
  tools?: string[];
  tools_invoked?: string[];
  /** 后端收口状态：failed_auth / failed_config / failed_permission / failed_internal 等 */
  status?: string;
  /** reused_prior_result：本步未调工具，复用了上一步已有结果 */
  outcome?: string;
  error?: string;
}

export type PlannedStepStatus = 'running' | 'done' | 'failed' | 'skipped';

export interface PlannedExecutionStepData {
  step_index: number;
  total_steps: number;
  objective: string;
  status: PlannedStepStatus;
  toolCallIds: string[];
  reusedPriorResult?: boolean;
  error?: string;
}

export interface PlannedExecutionState {
  steps: PlannedExecutionStepData[];
  currentStepIndex: number | null;
  pendingTools?: Array<{ id: string; stepIndex: number | null }>;
}

export const createPlannedExecutionState = (): PlannedExecutionState => ({
  steps: [],
  currentStepIndex: null,
  pendingTools: [],
});

const normalizeStepIndex = (value: unknown): number | null => {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n) || n < 1) return null;
  return Math.floor(n);
};

export const isFailedPlannedStepStatus = (status: unknown): boolean => {
  if (typeof status !== 'string' || !status) return false;
  return status === 'failed' || status.startsWith('failed_') || status === 'missing_params' || status === 'target_unresolved';
};

export const isSkippedPlannedStepStatus = (status: unknown): boolean =>
  status === 'skipped' || status === 'skipped_context_overflow';

export const applyPlannedExecutionStep = (
  state: PlannedExecutionState,
  event: PlannedExecutionStepEvent | Record<string, unknown> | null | undefined
): PlannedExecutionState => {
  if (!event || typeof event !== 'object') return state;
  const stepIndex = normalizeStepIndex(event.step_index);
  if (stepIndex == null) return state;
  const totalSteps = normalizeStepIndex(event.total_steps) ?? stepIndex;
  const objective = typeof event.objective === 'string' ? event.objective.trim() : '';
  const phase = typeof event.phase === 'string' ? event.phase : '';
  const endStatus: PlannedStepStatus = phase === 'end' && isFailedPlannedStepStatus(event.status)
    ? 'failed'
    : phase === 'end' && isSkippedPlannedStepStatus(event.status)
      ? 'skipped'
      : 'done';
  const endError = endStatus === 'failed' && typeof event.error === 'string'
    ? event.error.trim() || undefined
    : undefined;
  const steps = state.steps.map((step) => ({ ...step, toolCallIds: [...step.toolCallIds] }));
  const pendingTools = [...(state.pendingTools || [])];
  const existingIdx = steps.findIndex((step) => step.step_index === stepIndex);
  const syncTotal = (next: PlannedExecutionStepData[]) => {
    const latest = Math.max(totalSteps, next.length);
    return next.map((step) => ({ ...step, total_steps: latest }));
  };

  if (phase === 'end') {
    const reused = event.outcome === 'reused_prior_result';
    if (existingIdx >= 0) {
      steps[existingIdx] = {
        ...steps[existingIdx],
        objective: objective || steps[existingIdx].objective,
        status: endStatus,
        reusedPriorResult: reused || steps[existingIdx].reusedPriorResult,
        error: endError,
      };
    } else {
      steps.push({
        step_index: stepIndex,
        total_steps: totalSteps,
        objective: objective || getOpspilotTranslate()('chat.plannedStep.unnamed', '步骤 {index}', { index: stepIndex }),
        status: endStatus,
        toolCallIds: [],
        reusedPriorResult: reused,
        error: endError,
      });
      steps.sort((a, b) => a.step_index - b.step_index);
    }
    const keptAfterEnd: Array<{ id: string; stepIndex: number | null }> = [];
    for (const pending of pendingTools) {
      if (pending.stepIndex != null && pending.stepIndex !== stepIndex) {
        keptAfterEnd.push(pending);
        continue;
      }
      const target = steps.find((step) => step.step_index === stepIndex);
      if (target && !target.toolCallIds.includes(pending.id)) {
        target.toolCallIds.push(pending.id);
        target.reusedPriorResult = false;
      }
    }
    return {
      steps: syncTotal(steps),
      currentStepIndex: state.currentStepIndex === stepIndex ? null : state.currentStepIndex,
      pendingTools: keptAfterEnd,
    };
  }

  if (existingIdx >= 0) {
    steps[existingIdx] = { ...steps[existingIdx], objective: objective || steps[existingIdx].objective, status: 'running', error: undefined };
  } else {
    steps.push({
      step_index: stepIndex,
      total_steps: totalSteps,
      objective: objective || getOpspilotTranslate()('chat.plannedStep.unnamed', '步骤 {index}', { index: stepIndex }),
      status: 'running',
      toolCallIds: [],
    });
    steps.sort((a, b) => a.step_index - b.step_index);
  }
  const keptPending: Array<{ id: string; stepIndex: number | null }> = [];
  for (const pending of pendingTools) {
    if (pending.stepIndex != null && pending.stepIndex !== stepIndex) {
      keptPending.push(pending);
      continue;
    }
    const target = steps.find((step) => step.step_index === stepIndex);
    if (target && !target.toolCallIds.includes(pending.id)) {
      target.toolCallIds.push(pending.id);
      target.reusedPriorResult = false;
    }
  }
  return { steps: syncTotal(steps), currentStepIndex: stepIndex, pendingTools: keptPending };
};

export const attachToolCallToCurrentStep = (
  state: PlannedExecutionState,
  toolCallId: string,
  stepIndex?: number | null
): PlannedExecutionState => {
  if (!toolCallId) return state;
  const steps = state.steps.map((step) => ({ ...step, toolCallIds: [...step.toolCallIds] }));
  const pendingTools = [...(state.pendingTools || [])];
  const stamped = stepIndex != null && stepIndex >= 1 ? stepIndex : null;
  let target = stamped ?? state.currentStepIndex;
  if (target == null) {
    const running = steps.find((step) => step.status === 'running');
    target = running ? running.step_index : (steps.length === 1 ? steps[0].step_index : null);
  }
  if (target == null) {
    if (!pendingTools.some((item) => item.id === toolCallId)) {
      pendingTools.push({ id: toolCallId, stepIndex: stamped });
    }
    return { ...state, steps, pendingTools };
  }
  const index = steps.findIndex((step) => step.step_index === target);
  if (index < 0) {
    if (!pendingTools.some((item) => item.id === toolCallId)) {
      pendingTools.push({ id: toolCallId, stepIndex: target });
    }
    return { ...state, steps, pendingTools };
  }
  if (!steps[index].toolCallIds.includes(toolCallId)) {
    steps[index] = {
      ...steps[index],
      toolCallIds: [...steps[index].toolCallIds, toolCallId],
      reusedPriorResult: false,
    };
  }
  return { ...state, steps, pendingTools };
};

/** 事件没对上时，把还没挂进步骤的工具收进唯一一步或最后一步。 */
export function foldUnassignedTools(
  steps: PlannedExecutionStepData[],
  toolIds: string[],
): PlannedExecutionStepData[] {
  if (steps.length === 0 || toolIds.length === 0) {
    return steps;
  }
  const assigned = new Set(steps.flatMap((step) => step.toolCallIds));
  const loose = toolIds.filter((id) => id && !assigned.has(id));
  if (loose.length === 0) {
    return steps;
  }
  const targetIndex = steps.length === 1
    ? steps[0].step_index
    : steps[steps.length - 1].step_index;
  return steps.map((step) => (
    step.step_index === targetIndex
      ? {
        ...step,
        toolCallIds: [...step.toolCallIds, ...loose],
        reusedPriorResult: false,
      }
      : step
  ));
}

export const finalizePlannedExecutionSteps = (state: PlannedExecutionState): PlannedExecutionState => ({
  currentStepIndex: null,
  pendingTools: [],
  steps: state.steps.map((step) => (
    step.status === 'done' || step.status === 'failed' || step.status === 'skipped'
      ? step
      : { ...step, status: 'done' as const }
  )),
});

export const plannedStepIndexFromToolEvent = (
  event: { rawEvent?: unknown; raw_event?: unknown } | null | undefined
): number | null => {
  if (!event || typeof event !== 'object') return null;
  const raw = event.rawEvent ?? event.raw_event;
  if (!raw || typeof raw !== 'object') return null;
  const record = raw as { step_index?: unknown; stepIndex?: unknown };
  return normalizeStepIndex(record.step_index ?? record.stepIndex);
};


export const shouldExpandPlannedStep = (
  step: PlannedExecutionStepData,
  isStreaming: boolean
): boolean => {
  if (!isStreaming) {
    return false;
  }
  return step.status === 'running';
};

export const isToolAssignedToPlannedStep = (
  state: PlannedExecutionState | null | undefined,
  toolCallId: string
): boolean => {
  if (!state?.steps?.length || !toolCallId) {
    return false;
  }
  return state.steps.some((step) => step.toolCallIds.includes(toolCallId));
};
