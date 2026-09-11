import { isScreenModeEnabled, toSearchParams, withScreenQuery } from '@/console-layout';

export const buildOpsAnalysisViewHref = (
  type: string,
  id: string,
  currentSearch?: string | URLSearchParams | null,
): string => {
  const params = toSearchParams(currentSearch);
  params.set('type', type);
  params.set('id', id);
  return withScreenQuery(
    `/ops-analysis/view?${params.toString()}`,
    isScreenModeEnabled(currentSearch) || isScreenModeEnabled(params),
  );
};
