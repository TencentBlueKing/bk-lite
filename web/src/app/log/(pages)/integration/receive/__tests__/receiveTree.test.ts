import { describe, expect, it } from 'vitest';
import { buildReceiveTree } from '../receiveTree';

const categories = [
  { id: 'general', name: '通用' },
  { id: 'network', name: '网络' }
];

describe('receive tree for passive collect types', () => {
  it('hides snmp trap and counts syslog by source devices', () => {
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
      {
        allTitle: '全部',
        sourceDeviceCount: 4,
        sourceNodeTitle: (name) => `${name}来源`
      }
    );

    const general = tree.find((item) => item.key === 'general');
    expect(general?.children.map((item) => item.title)).toEqual([
      '系统日志来源(4)',
      '文件采集(2)'
    ]);
    expect(general?.children.find((item) => item.label === '系统日志来源')?.key).toBe('16');
    expect(general?.children.every((item) => item.children.length === 0)).toBe(true);
    expect(JSON.stringify(tree)).not.toContain('SNMP Trap');
  });
});
