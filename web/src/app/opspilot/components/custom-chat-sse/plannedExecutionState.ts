/**
 * DeepAgent planned_execution_step 状态机。
 * 将工具调用挂到当前执行步骤，供对话 UI 按方案 A（步骤嵌套工具组）渲染。
 */

export type PlannedStepStatus = 'running' | 'done' | 'failed' | 'skipped';

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

export interface PlannedExecutionStepData {
  step_index: number;
  total_steps: number;
  objective: string;
  status: PlannedStepStatus;
  toolCallIds: string[];
  /** 本步是否未调工具但复用了已有结果 */
  reusedPriorResult?: boolean;
  error?: string;
}

export interface PlannedExecutionState {
  steps: PlannedExecutionStepData[];
  /** 当前接收工具调用的步骤下标（1-based），无边界事件时为 null */
  currentStepIndex: number | null;
}

export const createPlannedExecutionState = (): PlannedExecutionState => ({
  steps: [],
  currentStepIndex: null,
});

const normalizeObjective = (objective: unknown): string => {
  if (typeof objective !== 'string') return '';
  return objective.trim();
};

const normalizeStepIndex = (value: unknown): number | null => {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n) || n < 1) return null;
  return Math.floor(n);
};

export const isFailedPlannedStepStatus = (status: unknown): boolean => {
  if (typeof status !== 'string' || !status) return false;
  return (
    status === 'failed' ||
    status.startsWith('failed_') ||
    status === 'missing_params' ||
    status === 'target_unresolved'
  );
};

export const isSkippedPlannedStepStatus = (status: unknown): boolean => {
  if (typeof status !== 'string' || !status) return false;
  return status === 'skipped' || status === 'skipped_context_overflow';
};

/**
 * 应用一条 planned_execution_step CUSTOM 事件。
 * start：创建或进入该步并标为 running；end：将该步标为 done / failed。
 */
export const applyPlannedExecutionStep = (
  state: PlannedExecutionState,
  event: PlannedExecutionStepEvent | null | undefined
): PlannedExecutionState => {
  if (!event || typeof event !== 'object') {
    return state;
  }

  const stepIndex = normalizeStepIndex(event.step_index);
  if (stepIndex == null) {
    return state;
  }

  const totalSteps = normalizeStepIndex(event.total_steps) ?? stepIndex;
  const objective = normalizeObjective(event.objective);
  const phase = typeof event.phase === 'string' ? event.phase : '';
  const endFailed = phase === 'end' && isFailedPlannedStepStatus(event.status);
  const endSkipped = phase === 'end' && isSkippedPlannedStepStatus(event.status);
  const endStatus: PlannedStepStatus = endFailed ? 'failed' : endSkipped ? 'skipped' : 'done';
  const endError =
    endFailed && typeof event.error === 'string' && event.error.trim()
      ? event.error.trim()
      : undefined;

  const steps = state.steps.map((step) => ({
    ...step,
    toolCallIds: [...step.toolCallIds],
  }));

  const existingIdx = steps.findIndex((step) => step.step_index === stepIndex);
  const syncTotalSteps = (nextSteps: PlannedExecutionStepData[]) => {
    const latestTotal = Math.max(totalSteps, nextSteps.length);
    return nextSteps.map((step) => ({ ...step, total_steps: latestTotal }));
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
        objective: objective || `步骤 ${stepIndex}`,
        status: endStatus,
        toolCallIds: [],
        reusedPriorResult: reused,
        error: endError,
      });
      steps.sort((a, b) => a.step_index - b.step_index);
    }

    return {
      steps: syncTotalSteps(steps),
      currentStepIndex: state.currentStepIndex === stepIndex ? null : state.currentStepIndex,
    };
  }

  // phase === 'start' 或未知 phase：视为进入该步
  if (existingIdx >= 0) {
    steps[existingIdx] = {
      ...steps[existingIdx],
      objective: objective || steps[existingIdx].objective,
      status: 'running',
      error: undefined,
    };
  } else {
    steps.push({
      step_index: stepIndex,
      total_steps: totalSteps,
      objective: objective || `步骤 ${stepIndex}`,
      status: 'running',
      toolCallIds: [],
    });
    steps.sort((a, b) => a.step_index - b.step_index);
  }

  return {
    steps: syncTotalSteps(steps),
    currentStepIndex: stepIndex,
  };
};

/** 从 TOOL_CALL_START.rawEvent 取出服务端盖上的步骤号。 */
export const plannedStepIndexFromToolEvent = (
  event: { rawEvent?: unknown; raw_event?: unknown } | null | undefined
): number | null => {
  if (!event || typeof event !== 'object') return null;
  const raw = event.rawEvent ?? event.raw_event;
  if (!raw || typeof raw !== 'object') return null;
  const record = raw as { step_index?: unknown; stepIndex?: unknown };
  return normalizeStepIndex(record.step_index ?? record.stepIndex);
};

/**
 * 将工具调用挂到步骤。
 * 有服务端步骤号时挂到那一步，即使该步已经 end。
 * 没有步骤号时挂当前步 / 仍 running 的步；仅剩一步且已结束时，晚到的工具仍挂到这一步。
 */
export const attachToolCallToCurrentStep = (
  state: PlannedExecutionState,
  toolCallId: string,
  stepIndex?: number | null
): PlannedExecutionState => {
  if (!toolCallId) {
    return state;
  }

  const stamped = normalizeStepIndex(stepIndex);
  let targetIndex = stamped ?? state.currentStepIndex;
  if (targetIndex == null) {
    const running = state.steps.find((step) => step.status === 'running');
    if (running) {
      targetIndex = running.step_index;
    }
  }
  if (targetIndex == null && state.steps.length === 1) {
    targetIndex = state.steps[0].step_index;
  }
  if (targetIndex == null) {
    return state;
  }

  const steps = state.steps.map((step) => ({
    ...step,
    toolCallIds: [...step.toolCallIds],
  }));
  const existingIdx = steps.findIndex((step) => step.step_index === targetIndex);
  if (existingIdx < 0) {
    if (stamped == null) {
      return state;
    }
    const totalSteps = steps.reduce((max, step) => Math.max(max, step.total_steps), stamped);
    steps.push({
      step_index: stamped,
      total_steps: totalSteps,
      objective: '',
      status: 'running',
      toolCallIds: [toolCallId],
    });
    steps.sort((a, b) => a.step_index - b.step_index);
    return { ...state, steps };
  }

  if (!steps[existingIdx].toolCallIds.includes(toolCallId)) {
    steps[existingIdx] = {
      ...steps[existingIdx],
      toolCallIds: [...steps[existingIdx].toolCallIds, toolCallId],
      reusedPriorResult: false,
    };
  }

  if (typeof console !== 'undefined' && typeof console.debug === 'function') {
    console.debug('[planned-execution] attach tool', {
      toolCallId,
      stamped: stamped ?? null,
      targetIndex,
      stepCount: steps.length,
    });
  }

  return {
    ...state,
    steps,
  };
};

/** 流式中仅展开 running 步；结束后默认全部收起。 */
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

/** 流结束时把仍 running 的步骤收口为 done；已失败的保持 failed。 */
export const finalizePlannedExecutionSteps = (
  state: PlannedExecutionState
): PlannedExecutionState => {
  if (!state.steps.length) {
    return state;
  }

  return {
    currentStepIndex: null,
    steps: state.steps.map((step) => {
      if (step.status === 'done' || step.status === 'failed' || step.status === 'skipped') {
        return step;
      }
      return { ...step, status: 'done' as const };
    }),
  };
};
