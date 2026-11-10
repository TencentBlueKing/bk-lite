import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  invalidateModelAttrListCache,
  loadCachedModelAttrList,
  loadCachedModelAttrListBatch,
  resetModelAttrListCache,
} from '../modelAttrListCache';

describe('model attr list cache', () => {
  beforeEach(() => {
    resetModelAttrListCache();
  });

  it('复用已完成结果，失效后重新请求', async () => {
    const fetcher = vi.fn(async (modelId: string) => [{ attr_id: modelId }]);
    const first = await loadCachedModelAttrList('zh-Hans', 'host', fetcher);
    const second = await loadCachedModelAttrList('zh-Hans', 'host', fetcher);
    expect(first).toEqual([{ attr_id: 'host' }]);
    expect(second).toEqual(first);
    expect(fetcher).toHaveBeenCalledTimes(1);

    invalidateModelAttrListCache('host');
    await loadCachedModelAttrList('zh-Hans', 'host', fetcher);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('进行中的同一模型只发一次请求', async () => {
    let resolveFetch: (value: { attr_id: string }[]) => void = () => undefined;
    const fetcher = vi.fn(() => new Promise<{ attr_id: string }[]>((resolve) => {
      resolveFetch = resolve;
    }));
    const first = loadCachedModelAttrList('zh-Hans', 'host', fetcher);
    const second = loadCachedModelAttrList('zh-Hans', 'host', fetcher);
    expect(fetcher).toHaveBeenCalledTimes(1);
    resolveFetch([{ attr_id: 'host' }]);
    await expect(Promise.all([first, second])).resolves.toEqual([
      [{ attr_id: 'host' }],
      [{ attr_id: 'host' }],
    ]);
  });

  it('批量查询跳过缓存并与单模型进行中请求合并', async () => {
    let resolveSingle: (value: { attr_id: string }[]) => void = () => undefined;
    const single = vi.fn(() => new Promise<{ attr_id: string }[]>((resolve) => {
      resolveSingle = resolve;
    }));
    const pendingSingle = loadCachedModelAttrList('zh-Hans', 'host', single);
    const batch = vi.fn(async (modelIds: string[]) => (
      Object.fromEntries(modelIds.map((modelId) => [modelId, [{ attr_id: modelId }]]))
    ));
    const loaded = loadCachedModelAttrListBatch('zh-Hans', ['host', 'mysql', 'host'], batch);
    expect(batch).toHaveBeenCalledTimes(1);
    expect(batch).toHaveBeenCalledWith(['mysql']);
    resolveSingle([{ attr_id: 'host' }]);
    await pendingSingle;
    await expect(loaded).resolves.toEqual({
      host: [{ attr_id: 'host' }],
      mysql: [{ attr_id: 'mysql' }],
    });
    expect(batch).toHaveBeenCalledTimes(1);
  });

  it('批量失败不写入缓存', async () => {
    const batch = vi.fn()
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValueOnce({ mysql: [{ attr_id: 'ip' }] });
    await expect(loadCachedModelAttrListBatch('zh-Hans', ['mysql'], batch)).rejects.toThrow('down');
    await expect(loadCachedModelAttrListBatch('zh-Hans', ['mysql'], batch)).resolves.toEqual({
      mysql: [{ attr_id: 'ip' }],
    });
    expect(batch).toHaveBeenCalledTimes(2);
  });

  it('不同语言不共用缓存', async () => {
    const batch = vi.fn(async () => ({ host: [{ attr_id: 'name' }] }));
    await loadCachedModelAttrListBatch('zh-Hans', ['host'], batch);
    await loadCachedModelAttrListBatch('en', ['host'], batch);
    expect(batch).toHaveBeenCalledTimes(2);
  });
});
