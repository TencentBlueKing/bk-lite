export const ENDPOINT_RED_CONCURRENCY = 6;

export const selectServicesForEndpointRed = <T extends { id: string }>(
  services: readonly T[],
  serviceId: string,
): T[] => {
  if (serviceId === 'all' || !serviceId) {
    return [...services];
  }
  return services.filter((service) => service.id === serviceId);
};

interface EndpointRedSettledOptions<R> {
  concurrency?: number;
  isCancelled?: () => boolean;
  onFulfilled?: (value: R, index: number) => void;
}

export const runEndpointRedSettled = async <T, R>(
  items: readonly T[],
  worker: (item: T, index: number) => Promise<R>,
  options: EndpointRedSettledOptions<R> = {},
): Promise<Array<PromiseSettledResult<R>>> => {
  const {
    concurrency = ENDPOINT_RED_CONCURRENCY,
    isCancelled = () => false,
    onFulfilled,
  } = options;
  if (!items.length) return [];

  const results = new Array<PromiseSettledResult<R>>(items.length);
  const workerCount = Math.min(Math.max(concurrency, 1), items.length);
  let cursor = 0;

  await Promise.all(
    Array.from({ length: workerCount }, async () => {
      while (cursor < items.length) {
        if (isCancelled()) return;
        const index = cursor;
        cursor += 1;
        try {
          const value = await worker(items[index], index);
          results[index] = { status: 'fulfilled', value };
          if (!isCancelled()) {
            onFulfilled?.(value, index);
          }
        } catch (reason) {
          results[index] = { status: 'rejected', reason };
        }
      }
    }),
  );

  return results.filter((result) => result !== undefined);
};
