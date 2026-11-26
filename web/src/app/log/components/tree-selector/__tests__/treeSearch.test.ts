import { describe, expect, it } from 'vitest';
import { TreeItem } from '@/app/log/types';
import {
  expandableTreeKeys,
  filterTreeByTitle,
  restoreMatchedBranches
} from '../treeSearch';

const tree: TreeItem[] = [
  {
    title: '通用',
    key: 'general',
    children: [
      {
        title: '系统日志',
        key: 'source-group:syslog',
        children: [
          { title: '来源设备(4)', key: '16', label: '来源设备', children: [] }
        ]
      },
      { title: '文件采集(2)', key: '3', label: '文件采集', children: [] }
    ]
  }
];

describe('log tree search', () => {
  it('expands every branch, including a source-device group', () => {
    expect(expandableTreeKeys(tree)).toEqual(['general', 'source-group:syslog']);
  });

  it('keeps the source-device leaf when the system-log group title matches', () => {
    const filtered = filterTreeByTitle(tree, '系统日志');
    const restored = restoreMatchedBranches(filtered, tree, '系统日志');
    const group = restored[0].children[0];
    expect(group.title).toBe('系统日志');
    expect(group.children.map((item) => item.title)).toEqual(['来源设备(4)']);
    expect(expandableTreeKeys(restored)).toEqual(['general', 'source-group:syslog']);
  });

  it('keeps only the matching sibling when searching a collect type', () => {
    const filtered = filterTreeByTitle(tree, '文件');
    const restored = restoreMatchedBranches(filtered, tree, '文件');
    expect(restored[0].children.map((item) => item.title)).toEqual(['文件采集(2)']);
  });
});
