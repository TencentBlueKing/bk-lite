export const NETWORK_STATUS_TOPOLOGY_INSTANCE_PAGE_SIZE = 20;

export interface NetworkDeviceModelCount {
  modelId: string;
  count: number;
}

export interface NetworkDevicePageSlice {
  modelId: string;
  requestPage: number;
  pageSize: number;
  sliceStart: number;
  take: number;
}

export const collectSettledModelCounts = (
  modelIds: string[],
  results: PromiseSettledResult<{ count?: number } | null | undefined>[],
): NetworkDeviceModelCount[] =>
  modelIds.map((modelId, index) => {
    const result = results[index];
    if (!result || result.status !== 'fulfilled' || !result.value) {
      return { modelId, count: 0 };
    }
    return {
      modelId,
      count: Math.max(0, Number(result.value.count) || 0),
    };
  });

export const sumModelCounts = (models: NetworkDeviceModelCount[]) =>
  models.reduce((sum, item) => sum + item.count, 0);

export const planCrossModelInstancePage = (
  models: NetworkDeviceModelCount[],
  page: number,
  pageSize: number,
): NetworkDevicePageSlice[] => {
  if (page < 1 || pageSize < 1) return [];

  let skip = (page - 1) * pageSize;
  let remaining = pageSize;
  const slices: NetworkDevicePageSlice[] = [];

  models.forEach((model) => {
    if (remaining <= 0 || model.count <= 0) return;
    if (skip >= model.count) {
      skip -= model.count;
      return;
    }

    let localOffset = skip;
    skip = 0;
    let take = Math.min(model.count - localOffset, remaining);
    remaining -= take;

    while (take > 0) {
      const requestPage = Math.floor(localOffset / pageSize) + 1;
      const sliceStart = localOffset % pageSize;
      const inPage = Math.min(pageSize - sliceStart, take);
      slices.push({
        modelId: model.modelId,
        requestPage,
        pageSize,
        sliceStart,
        take: inPage,
      });
      localOffset += inPage;
      take -= inPage;
    }
  });

  return slices;
};

export const uniqueInstancePageRequests = (slices: NetworkDevicePageSlice[]) => {
  const seen = new Set<string>();
  const requests: Array<{
    modelId: string;
    requestPage: number;
    pageSize: number;
  }> = [];

  slices.forEach((slice) => {
    const key = `${slice.modelId}:${slice.requestPage}`;
    if (seen.has(key)) return;
    seen.add(key);
    requests.push({
      modelId: slice.modelId,
      requestPage: slice.requestPage,
      pageSize: slice.pageSize,
    });
  });

  return requests;
};

export const applyInstancePageSlices = (
  slices: NetworkDevicePageSlice[],
  pagesByKey: Map<string, unknown[]>,
): unknown[] =>
  slices.flatMap((slice) => {
    const rows = pagesByKey.get(`${slice.modelId}:${slice.requestPage}`) || [];
    return rows.slice(slice.sliceStart, slice.sliceStart + slice.take);
  });

export const mergePageSelection = (
  previous: string[],
  pageIds: string[],
  selectedOnPage: string[],
  limit: number,
): { next: string[]; truncated: boolean } => {
  const pageSet = new Set(pageIds);
  const selectedOnPageSet = new Set(selectedOnPage);
  const next: string[] = [];
  const seen = new Set<string>();
  let truncated = false;
  const safeLimit = Math.max(0, limit);

  const push = (id: string) => {
    if (!id || seen.has(id)) return;
    if (next.length >= safeLimit) {
      truncated = true;
      return;
    }
    seen.add(id);
    next.push(id);
  };

  previous.forEach((id) => {
    if (pageSet.has(id) && !selectedOnPageSet.has(id)) return;
    push(id);
  });
  selectedOnPage.forEach(push);

  return { next, truncated };
};
