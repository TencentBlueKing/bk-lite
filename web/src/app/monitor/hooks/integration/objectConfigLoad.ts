export type ObjectConfigLoadStatus = 'waiting' | 'ready' | 'error';

export interface ObjectConfigLoadState {
  status: ObjectConfigLoadStatus;
  generation: number;
}

export const createObjectConfigLoadState = (input: {
  objectName?: string | null;
  cached?: boolean;
}): ObjectConfigLoadState => {
  if (!input.objectName || input.cached) {
    return { status: 'ready', generation: 0 };
  }
  return { status: 'waiting', generation: 0 };
};

export const applyObjectConfigLoadSuccess = (
  state: ObjectConfigLoadState,
  generation: number
): ObjectConfigLoadState => {
  if (generation !== state.generation) {
    return state;
  }
  return { ...state, status: 'ready' };
};

export const applyObjectConfigLoadReject = (
  state: ObjectConfigLoadState,
  generation: number
): ObjectConfigLoadState => {
  if (generation !== state.generation) {
    return state;
  }
  return { ...state, status: 'error' };
};

export const retryObjectConfigLoad = (
  state: ObjectConfigLoadState
): ObjectConfigLoadState => ({
  status: 'waiting',
  generation: state.generation + 1,
});

export const switchObjectConfigLoad = (
  state: ObjectConfigLoadState,
  input: { objectName?: string | null; cached?: boolean }
): ObjectConfigLoadState => {
  const generation = state.generation + 1;
  if (!input.objectName || input.cached) {
    return { status: 'ready', generation };
  }
  return { status: 'waiting', generation };
};

export const canOpenObjectConfigForm = (state: ObjectConfigLoadState): boolean =>
  state.status === 'ready';
