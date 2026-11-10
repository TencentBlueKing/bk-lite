export const MODEL_ATTR_LIST_BATCH_LIMIT = 50;

type AttrList = any[];
type AttrFetcher = (modelId: string) => Promise<AttrList | null | undefined>;
type BatchFetcher = (modelIds: string[]) => Promise<Record<string, AttrList | null | undefined>>;

const cache = new Map<string, AttrList>();
const inflight = new Map<string, Promise<AttrList>>();

const cacheKey = (locale: string, modelId: string) => `${locale}\0${modelId}`;

const asList = (attrs: AttrList | null | undefined): AttrList => (
  Array.isArray(attrs) ? attrs : []
);

const readCache = (locale: string, modelId: string): AttrList | undefined => {
  const hit = cache.get(cacheKey(locale, modelId));
  return hit ? hit.slice() : undefined;
};

const matchesModel = (key: string, modelId: string) => key.endsWith(`\0${modelId}`);

export const invalidateModelAttrListCache = (modelId?: string) => {
  if (!modelId) {
    cache.clear();
    inflight.clear();
    return;
  }
  for (const key of cache.keys()) {
    if (matchesModel(key, modelId)) cache.delete(key);
  }
  for (const key of inflight.keys()) {
    if (matchesModel(key, modelId)) inflight.delete(key);
  }
};

export const resetModelAttrListCache = () => {
  cache.clear();
  inflight.clear();
};

const remember = (locale: string, modelId: string, attrs: AttrList | null | undefined) => {
  const list = asList(attrs);
  cache.set(cacheKey(locale, modelId), list);
  return list.slice();
};

export const loadCachedModelAttrList = (
  locale: string,
  modelId: string,
  fetcher: AttrFetcher,
): Promise<AttrList> => {
  const cached = readCache(locale, modelId);
  if (cached) return Promise.resolve(cached);
  const key = cacheKey(locale, modelId);
  const pending = inflight.get(key);
  if (pending) return pending.then((attrs) => attrs.slice());

  const request = fetcher(modelId)
    .then((attrs) => {
      if (inflight.get(key) !== request) return asList(attrs).slice();
      return remember(locale, modelId, attrs);
    })
    .finally(() => {
      if (inflight.get(key) === request) inflight.delete(key);
    });
  inflight.set(key, request);
  return request;
};

const chunkIds = (modelIds: string[]) => {
  const chunks: string[][] = [];
  for (let index = 0; index < modelIds.length; index += MODEL_ATTR_LIST_BATCH_LIMIT) {
    chunks.push(modelIds.slice(index, index + MODEL_ATTR_LIST_BATCH_LIMIT));
  }
  return chunks;
};

export const loadCachedModelAttrListBatch = async (
  locale: string,
  modelIds: string[],
  fetcher: BatchFetcher,
): Promise<Record<string, AttrList>> => {
  const result: Record<string, AttrList> = {};
  const missing: string[] = [];
  const seen = new Set<string>();
  const jobs: Promise<unknown>[] = [];

  modelIds.forEach((modelId) => {
    if (!modelId || seen.has(modelId)) return;
    seen.add(modelId);
    const cached = readCache(locale, modelId);
    if (cached) {
      result[modelId] = cached;
      return;
    }
    const pending = inflight.get(cacheKey(locale, modelId));
    if (pending) {
      jobs.push(pending.then((attrs) => {
        result[modelId] = attrs.slice();
      }));
      return;
    }
    missing.push(modelId);
  });

  chunkIds(missing).forEach((chunk) => {
    const owned = new Map<string, Promise<AttrList>>();
    const request = fetcher(chunk)
      .then((payload) => {
        chunk.forEach((modelId) => {
          const key = cacheKey(locale, modelId);
          if (inflight.get(key) !== owned.get(modelId)) return;
          result[modelId] = remember(locale, modelId, payload?.[modelId]);
        });
        return payload;
      })
      .finally(() => {
        chunk.forEach((modelId) => {
          const key = cacheKey(locale, modelId);
          if (inflight.get(key) === owned.get(modelId)) inflight.delete(key);
        });
      });

    chunk.forEach((modelId) => {
      const slot = request.then((payload) => asList(payload?.[modelId]).slice());
      // 批量请求自己会接住失败；这条分支只给后来的单模型调用复用，不能变成未处理拒绝。
      void slot.catch(() => undefined);
      owned.set(modelId, slot);
      inflight.set(cacheKey(locale, modelId), slot);
    });
    jobs.push(request.then(() => {
      chunk.forEach((modelId) => {
        if (!result[modelId]) result[modelId] = readCache(locale, modelId) || [];
      });
    }));
  });

  await Promise.all(jobs);
  return result;
};
