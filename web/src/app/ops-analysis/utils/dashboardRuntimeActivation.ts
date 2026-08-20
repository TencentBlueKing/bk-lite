import type { RuntimeRequestPriority } from '@/app/ops-analysis/utils/dashboardRuntimeScheduler';

export interface RuntimeActivationState {
  active: boolean;
  priority: RuntimeRequestPriority;
}

interface VerticalBounds {
  top: number;
  bottom: number;
}

export const resolveRuntimeActivation = ({
  root,
  widget,
  activationMargin,
  order,
}: {
  root: VerticalBounds;
  widget: VerticalBounds;
  activationMargin: number;
  order: number;
}): RuntimeActivationState => {
  const visible = widget.bottom >= root.top && widget.top <= root.bottom;
  const active = widget.bottom >= root.top - activationMargin
    && widget.top <= root.bottom + activationMargin;
  const distance = visible
    ? 0
    : widget.top > root.bottom
      ? widget.top - root.bottom
      : root.top - widget.bottom;

  return {
    active,
    priority: {
      cause: 1,
      visibility: visible ? 0 : 1,
      distance: Math.max(0, distance),
      order,
    },
  };
};

export const activateAllRuntimeWidgets = (
  widgetIds: string[],
): Record<string, RuntimeActivationState> =>
  widgetIds.reduce<Record<string, RuntimeActivationState>>((result, id, order) => {
    result[id] = {
      active: true,
      priority: { cause: 1, visibility: 0, distance: 0, order },
    };
    return result;
  }, {});

const runtimeStateRenderKey = (state: RuntimeActivationState) =>
  `${Number(state.active)}:${state.priority.visibility}:${state.priority.order}`;

export const shouldCommitRuntimeStates = (
  previous: Record<string, RuntimeActivationState>,
  next: Record<string, RuntimeActivationState>,
) => {
  const previousIds = Object.keys(previous);
  const nextIds = Object.keys(next);
  if (previousIds.length !== nextIds.length) {
    return true;
  }
  return nextIds.some((id) => {
    const previousState = previous[id];
    const nextState = next[id];
    if (!previousState || !nextState) {
      return true;
    }
    return runtimeStateRenderKey(previousState) !== runtimeStateRenderKey(nextState);
  });
};
