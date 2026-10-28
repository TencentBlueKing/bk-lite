import { describe, expect, it } from 'vitest';

import {
  RECENT_CANVAS_STORAGE_KEY,
  readRecentCanvases,
  recordRecentCanvas,
  renameRecentCanvas,
} from '../recentCanvasStorage';

const memoryStorage = () => {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
  };
};

describe('rename recent canvas', () => {
  it('updates the stored title and keeps order and viewed time', () => {
    const storage = memoryStorage();
    recordRecentCanvas(storage, {
      id: 'topology_2',
      dataId: '2',
      type: 'topology',
      name: '旧拓扑',
    });
    recordRecentCanvas(storage, {
      id: 'dashboard_9',
      dataId: '9',
      type: 'dashboard',
      name: '旧仪表盘',
    });
    const before = readRecentCanvases(storage);

    const next = renameRecentCanvas(storage, {
      id: 'dashboard_9',
      dataId: '9',
      type: 'dashboard',
      name: '新仪表盘',
    });

    expect(next.map((item) => item.name)).toEqual(['新仪表盘', '旧拓扑']);
    expect(next.map((item) => item.viewedAt)).toEqual(before.map((item) => item.viewedAt));
    expect(next[0]).toMatchObject({
      id: 'dashboard_9',
      dataId: '9',
      type: 'dashboard',
      name: '新仪表盘',
    });
    expect(JSON.parse(storage.getItem(RECENT_CANVAS_STORAGE_KEY) || '[]')[0].name).toBe('新仪表盘');
  });

  it('matches a recent entry by canvas id when the tree id differs', () => {
    const storage = memoryStorage();
    recordRecentCanvas(storage, {
      id: 'dashboard_9',
      dataId: '9',
      type: 'dashboard',
      name: '旧仪表盘',
    });

    const next = renameRecentCanvas(storage, {
      id: 'other-tree-id',
      dataId: '9',
      type: 'dashboard',
      name: '新仪表盘',
    });

    expect(next).toEqual([
      expect.objectContaining({ id: 'dashboard_9', dataId: '9', name: '新仪表盘' }),
    ]);
  });
});
