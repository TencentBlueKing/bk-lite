export interface TargetLiveOutput {
  stdout: string;
  stderr: string;
  status?: string;
  done: boolean;
}

export type LiveOutputMap = Record<string, TargetLiveOutput>;

export interface StreamEventPayload {
  execution_id?: string;
  target_key?: string;
  stream?: 'stdout' | 'stderr';
  line?: string;
  type?: string;
  status?: string;
  message?: string;
  dropped_lines?: number;
}

const MAX_CHARS_PER_TARGET = 500_000;

function appendCapped(prev: string, chunk: string): string {
  const next = prev + chunk;
  if (next.length <= MAX_CHARS_PER_TARGET) return next;
  return next.slice(next.length - MAX_CHARS_PER_TARGET);
}

export function applyExecutionStreamEvent(
  prev: LiveOutputMap,
  payload: StreamEventPayload
): LiveOutputMap {
  const targetKey = payload.target_key;
  if (!targetKey) return prev;

  const cur: TargetLiveOutput = prev[targetKey] || {
    stdout: '',
    stderr: '',
    done: false,
  };
  const next: TargetLiveOutput = { ...cur };
  if (payload.type === 'done') {
    next.done = true;
    if (payload.status) next.status = payload.status;
  } else if (payload.line != null) {
    const chunk = payload.line + '\n';
    if (payload.stream === 'stderr') {
      next.stderr = appendCapped(cur.stderr, chunk);
    } else {
      next.stdout = appendCapped(cur.stdout, chunk);
    }
  }
  return { ...prev, [targetKey]: next };
}
