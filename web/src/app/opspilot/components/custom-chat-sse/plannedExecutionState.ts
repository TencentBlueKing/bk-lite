/**
 * DeepAgent planned_execution_step 状态机。
 * 将工具调用挂到当前执行步骤，供对话 UI 按方案 A（步骤嵌套工具组）渲染。
 */

export type PlannedStepStatus = 'running' | 'done' | 'failed';

export interface PlannedExecutionStepEvent {
  phase: 'start' | 'end' | string;
  step_index: number;
  total_steps: number;
  objective: string;
  tools?: string[];
  /** 后端收口状态：failed_auth / failed_config / failed_permission / failed_internal 等 */
  status?: string;
  error?: string;
}

export interface PlannedExecutionStepData {
  step_index: number;
  total_steps: number;
  objective: string;
  status: PlannedStepStatus;
  toolCallIds: string[];
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
  return status === 'failed' || status.startsWith('failed_');
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
  const endStatus: PlannedStepStatus = endFailed ? 'failed' : 'done';
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
    if (existingIdx >= 0) {
      steps[existingIdx] = {
        ...steps[existingIdx],
        objective: objective || steps[existingIdx].objective,
        status: endStatus,
        error: endError,
      };
    } else {
      steps.push({
        step_index: stepIndex,
        total_steps: totalSteps,
        objective: objective || `步骤 ${stepIndex}`,
        status: endStatus,
        toolCallIds: [],
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

/**
 * 将工具调用挂到当前步骤。
 * 若步骤已 end（currentStepIndex 为空）但已有步骤，挂到最近一步，
 * 兼容 chain_end 补发 TOOL_CALL 晚于 planned_execution_step end 的时序。
 */
export const attachToolCallToCurrentStep = (
  state: PlannedExecutionState,
  toolCallId: string
): PlannedExecutionState => {
  if (!toolCallId) {
    return state;
  }

  let targetIndex = state.currentStepIndex;
  if (targetIndex == null && state.steps.length > 0) {
    targetIndex = Math.max(...state.steps.map((step) => step.step_index));
  }
  if (targetIndex == null) {
    return state;
  }

  const steps = state.steps.map((step) => {
    if (step.step_index !== targetIndex) {
      return { ...step, toolCallIds: [...step.toolCallIds] };
    }
    if (step.toolCallIds.includes(toolCallId)) {
      return { ...step, toolCallIds: [...step.toolCallIds] };
    }
    return {
      ...step,
      toolCallIds: [...step.toolCallIds, toolCallId],
    };
  });

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
      if (step.status === 'done' || step.status === 'failed') {
        return step;
      }
      return { ...step, status: 'done' as const };
    }),
  };
};
