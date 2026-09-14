export interface K8sMetaAutoFetchInput {
  isK8sSource: boolean;
  hasMeta: boolean;
  loading: boolean;
  failed: boolean;
}

export interface K8sMetaFetchSnapshot<T> {
  meta?: T;
  loading: boolean;
  failed: boolean;
}

export type K8sMetaFetchOutcome<T> =
  | { status: 'success'; meta: T }
  | { status: 'failure' }
  | { status: 'retry' }
  | { status: 'reset' };

export function shouldAutoFetchK8sMeta(input: K8sMetaAutoFetchInput): boolean {
  return Boolean(input.isK8sSource && !input.hasMeta && !input.loading && !input.failed);
}

export function applyK8sMetaFetchResult<T>(
  snapshot: K8sMetaFetchSnapshot<T>,
  outcome: K8sMetaFetchOutcome<T>,
  options?: { cancelled?: boolean },
): K8sMetaFetchSnapshot<T> {
  if (options?.cancelled) {
    return snapshot;
  }

  switch (outcome.status) {
    case 'success':
      return { meta: outcome.meta, loading: false, failed: false };
    case 'failure':
      return { ...snapshot, loading: false, failed: true };
    case 'retry':
      return { ...snapshot, loading: false, failed: false };
    case 'reset':
      return { meta: undefined, loading: false, failed: false };
    default:
      return snapshot;
  }
}
