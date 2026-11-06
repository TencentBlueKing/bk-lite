import { describe, expect, it } from 'vitest';
import {
  CMDB_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY,
  MONITOR_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY,
  omitEmptyCountedNodes,
  omitEmptyModelGroups,
  readHideEmptyModels,
  treeHasInstanceCounts,
  writeHideEmptyModels,
} from '../emptyModelTree';

describe('空模型显隐偏好', () => {
  it('使用约定的 localStorage 键', () => {
    expect(CMDB_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY).toBe('cmdb_object_tree_hide_empty_model');
    expect(MONITOR_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY).toBe('monitor_object_tree_hide_empty_model');
  });

  it('缺省、false 和非法值都表示显示空模型', () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
    };

    expect(readHideEmptyModels(storage, CMDB_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY)).toBe(false);
    storage.setItem(CMDB_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY, 'false');
    expect(readHideEmptyModels(storage, CMDB_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY)).toBe(false);
    storage.setItem(CMDB_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY, 'TRUE');
    expect(readHideEmptyModels(storage, CMDB_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY)).toBe(false);
    storage.setItem(CMDB_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY, '1');
    expect(readHideEmptyModels(storage, CMDB_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY)).toBe(false);
  });

  it('把 true / false 写回存储，并在下次读取时生效', () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
    };

    expect(writeHideEmptyModels(storage, MONITOR_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY, true)).toBe(true);
    expect(values.get(MONITOR_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY)).toBe('true');
    expect(readHideEmptyModels(storage, MONITOR_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY)).toBe(true);

    writeHideEmptyModels(storage, MONITOR_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY, false);
    expect(values.get(MONITOR_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY)).toBe('false');
    expect(readHideEmptyModels(storage, MONITOR_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY)).toBe(false);
  });

  it('存储不可用时保持显示空模型，且不抛错', () => {
    const denied = {
      getItem: () => {
        throw new Error('denied');
      },
      setItem: () => {
        throw new Error('denied');
      },
    };

    expect(readHideEmptyModels(null, CMDB_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY)).toBe(false);
    expect(readHideEmptyModels(denied, CMDB_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY)).toBe(false);
    expect(writeHideEmptyModels(null, CMDB_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY, true)).toBe(false);
    expect(writeHideEmptyModels(denied, CMDB_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY, true)).toBe(false);
  });
});

describe('omitEmptyCountedNodes', () => {
  const nodes = [
    {
      key: 'all',
      children: [],
    },
    {
      key: 'os',
      children: [
        { key: 'host', count: 3, children: [] },
        { key: 'process', count: 0, children: [] },
      ],
    },
    {
      key: 'cloud',
      children: [
        {
          key: 'account',
          count: 0,
          children: [
            { key: 'vm', count: 2, children: [] },
            { key: 'disk', count: 0, children: [] },
          ],
        },
      ],
    },
    {
      key: 'db',
      children: [{ key: 'mysql', count: 0, children: [] }],
    },
  ];

  it('去掉无实例模型，并保留有实例子节点的空父模型', () => {
    expect(omitEmptyCountedNodes(nodes)).toEqual([
      { key: 'all', children: [] },
      {
        key: 'os',
        children: [{ key: 'host', count: 3, children: [] }],
      },
      {
        key: 'cloud',
        children: [
          {
            key: 'account',
            count: 0,
            children: [{ key: 'vm', count: 2, children: [] }],
          },
        ],
      },
    ]);
  });

  it('只有带实例计数的树才显示控制', () => {
    expect(treeHasInstanceCounts(nodes)).toBe(true);
    expect(treeHasInstanceCounts([{ key: 'all', children: [] }])).toBe(false);
  });
});

describe('omitEmptyModelGroups', () => {
  it('去掉无实例模型以及因此变空的分组，且不修改原分组', () => {
    const groups = [
      {
        classification_id: 'os',
        list: [{ model_id: 'host' }, { model_id: 'process' }],
      },
      {
        classification_id: 'db',
        list: [{ model_id: 'mysql' }],
      },
    ];

    expect(omitEmptyModelGroups(groups, { host: 11, process: 0 })).toEqual([
      {
        classification_id: 'os',
        list: [{ model_id: 'host' }],
      },
    ]);
    expect(groups[0].list).toHaveLength(2);
  });

  it('计数缺失或还没返回时，把模型视为空模型', () => {
    const groups = [{ classification_id: 'os', list: [{ model_id: 'host' }] }];
    expect(omitEmptyModelGroups(groups, {})).toEqual([]);
    expect(omitEmptyModelGroups(groups, null)).toEqual([]);
  });
});
