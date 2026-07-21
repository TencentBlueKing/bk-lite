export type TopNContentState = 'loading' | 'error' | 'empty' | 'ready';

export const resolveTopNContentState = ({
  loading,
  errorMessage,
  hasRows,
}: {
  loading: boolean;
  errorMessage?: string;
  hasRows: boolean;
}): TopNContentState => {
  if (loading) return 'loading';
  if (errorMessage) return 'error';
  return hasRows ? 'ready' : 'empty';
};

export const isTopNContentReady = (state: TopNContentState): boolean =>
  state === 'ready' || state === 'empty';
