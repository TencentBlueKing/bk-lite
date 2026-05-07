const inflightRequests = new Map<string, Promise<unknown>>();

const sortValue = (value: unknown): unknown => {
  if (Array.isArray(value)) {
    return value.map(sortValue);
  }

  if (value && typeof value === 'object') {
    return Object.keys(value as Record<string, unknown>)
      .sort()
      .reduce<Record<string, unknown>>((acc, key) => {
        acc[key] = sortValue((value as Record<string, unknown>)[key]);
        return acc;
      }, {});
  }

  return value;
};

export const buildRequestDedupKey = (
  dataSourceId: number,
  params?: Record<string, unknown>,
): string => {
  const normalizedParams = params ? JSON.stringify(sortValue(params)) : '{}';
  return `${dataSourceId}:${normalizedParams}`;
};

export const dedupeInFlightRequest = async <T>(
  key: string,
  requestFactory: () => Promise<T>,
): Promise<T> => {
  const existingRequest = inflightRequests.get(key);
  if (existingRequest) {
    return existingRequest as Promise<T>;
  }

  const request = requestFactory().finally(() => {
    inflightRequests.delete(key);
  });

  inflightRequests.set(key, request);
  return request;
};
