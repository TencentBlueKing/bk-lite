import { ObjectItem } from '@/app/monitor/types';

/** 监控对象会话缓存:集成列表左侧树可复用,拖拽排序后需 invalidate */
let cachedObjects: ObjectItem[] | null = null;
let inflight: Promise<ObjectItem[]> | null = null;

export const getCachedMonitorObjects = (): ObjectItem[] | null => cachedObjects;

export const setCachedMonitorObjects = (objects: ObjectItem[]) => {
  cachedObjects = objects;
};

export const invalidateMonitorObjectsCache = () => {
  cachedObjects = null;
  inflight = null;
};

export const loadMonitorObjectsCached = async (
  fetcher: () => Promise<ObjectItem[]>
): Promise<ObjectItem[]> => {
  if (cachedObjects) {
    return cachedObjects;
  }
  if (inflight) {
    return inflight;
  }
  inflight = (async () => {
    const data = await fetcher();
    const list = Array.isArray(data) ? data : [];
    cachedObjects = list;
    return list;
  })();
  try {
    return await inflight;
  } finally {
    inflight = null;
  }
};
