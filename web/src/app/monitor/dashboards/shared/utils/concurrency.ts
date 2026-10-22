/** 可选 `signal`：中止后不再领取新任务；不传时保持原有排空行为，Host 等调用方不受影响。 */
export const runWithConcurrency = async <T, R>(
  items: T[],
  limit: number,
  worker: (item: T, index: number) => Promise<R>,
  signal?: AbortSignal
): Promise<R[]> => {
  const results = new Array<R>(items.length);
  let cursor = 0;
  const workerCount = Math.min(Math.max(limit, 1), items.length);

  await Promise.all(
    Array.from({ length: workerCount }, async () => {
      while (cursor < items.length) {
        if (signal?.aborted) {
          return;
        }
        const index = cursor;
        cursor += 1;
        results[index] = await worker(items[index], index);
      }
    })
  );

  return results;
};
