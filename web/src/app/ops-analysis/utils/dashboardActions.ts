import type {
  DashboardActionParamMapping,
} from '@/app/ops-analysis/types/dashBoard';

export const OPERATION_COLUMN_KEY_PREFIX = '__actions__';

export const createOperationColumnKey = (
  columns: Array<{ key?: string }>,
): string => {
  const existingKeys = new Set(
    columns.map((column) => column.key).filter(Boolean),
  );

  if (!existingKeys.has(OPERATION_COLUMN_KEY_PREFIX)) {
    return OPERATION_COLUMN_KEY_PREFIX;
  }

  let index = 2;
  while (existingKeys.has(`__actions_${index}__`)) {
    index += 1;
  }

  return `__actions_${index}__`;
};

export const buildDashboardActionUrl = (
  rawUrl: string | undefined,
  params: Record<string, string | number | boolean>,
): string => {
  const url = rawUrl?.trim();
  if (!url) return '';

  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') {
      return;
    }
    searchParams.set(key, String(value));
  });

  const queryString = searchParams.toString();
  if (!queryString) return url;

  const [urlWithoutHash, hash = ''] = url.split('#');
  const separator = urlWithoutHash.includes('?') ? '&' : '?';
  const hashFragment = hash ? `#${hash}` : '';

  return `${urlWithoutHash}${separator}${queryString}${hashFragment}`;
};

export const resolveDashboardActionParams = (
  mappings: DashboardActionParamMapping[] | undefined,
  record: Record<string, any>,
): Record<string, string | number | boolean> => {
  const params: Record<string, string | number | boolean> = {};

  (mappings || []).forEach((mapping) => {
    if (!mapping.key) {
      return;
    }

    if (mapping.source === 'rowField') {
      const value = mapping.sourceKey ? record?.[mapping.sourceKey] : undefined;
      if (value === null || value === undefined || value === '') {
        return;
      }
      if (['string', 'number', 'boolean'].includes(typeof value)) {
        params[mapping.key] = value;
      } else {
        params[mapping.key] = String(value);
      }
      return;
    }

    if (
      mapping.source === 'fixed' &&
      mapping.value !== null &&
      mapping.value !== undefined &&
      mapping.value !== ''
    ) {
      params[mapping.key] = mapping.value;
    }
  });

  return params;
};
