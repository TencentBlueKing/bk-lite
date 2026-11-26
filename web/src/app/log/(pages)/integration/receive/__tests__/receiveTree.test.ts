import { describe, expect, it } from 'vitest';
import { buildReceiveTree } from '../receiveTree';

const categories = [
  { id: 'general', name: '通用' },
  { id: 'network', name: '网络' }
];

describe('receive tree', () => {
  it('lists only collect types that have collect instances', () => {
    const tree = buildReceiveTree(
      [
        {
          id: 14,
          name: 'snmp_trap',
          display_name: 'SNMP Trap',
          display_category: 'general',
          instance_count: 0
        },
        {
          id: 16,
          name: 'syslog',
          display_name: '系统日志',
          display_category: 'general',
          instance_count: 0
        },
        {
          id: 3,
          name: 'file',
          display_name: '文件采集',
          display_category: 'general',
          instance_count: 2
        }
      ],
      categories,
      '全部'
    );

    expect(tree[0]).toEqual({ title: '全部', key: 'all', children: [] });
    const general = tree.find((item) => item.key === 'general');
    expect(general?.children.map((item) => item.title)).toEqual(['文件采集(2)']);
    expect(JSON.stringify(tree)).not.toContain('SNMP Trap');
    expect(JSON.stringify(tree)).not.toContain('系统日志');
  });
});
