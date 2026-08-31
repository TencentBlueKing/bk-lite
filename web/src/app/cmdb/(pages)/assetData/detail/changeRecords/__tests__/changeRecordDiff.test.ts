import { describe, expect, it } from 'vitest';

import { buildChangeRecordDiffRows } from '../changeRecordDiff';

describe('buildChangeRecordDiffRows', () => {
  it('表格字段展示列名和实际值，不泄漏对象默认字符串', () => {
    const rows = buildChangeRecordDiffRows(
      {
        label: 'instance',
        before_data: {
          network_cards: [{ name: 'eth0', mac: '00:11:22:33:44:55' }],
        },
        after_data: {
          network_cards: [{ name: 'eth0', mac: '00:11:22:33:44:66' }],
        },
      },
      {
        network_cards: [{ name: 'eth0', mac: '00:11:22:33:44:77' }],
      },
      {
        network_cards: {
          attr_name: '网卡',
          attr_type: 'table',
          option: [
            {
              column_id: 'name',
              column_name: '名称',
              column_type: 'str',
              order: 1,
            },
            {
              column_id: 'mac',
              column_name: 'MAC 地址',
              column_type: 'str',
              order: 2,
            },
          ],
        },
      }
    );

    expect(rows).toHaveLength(1);
    expect(rows[0].before).toContain('eth0');
    expect(rows[0].before).toContain('00:11:22:33:44:55');
    expect(rows[0].before).toBe('名称：eth0；MAC 地址：00:11:22:33:44:55');
    expect(rows[0].before).not.toContain('[object Object]');
    expect(rows[0].after).not.toContain('[object Object]');
    expect(rows[0].current).not.toContain('[object Object]');
    expect(rows[0].changed).toBe(true);
    expect(rows[0].currentDiff).toBe(true);
  });

  it('表格字段兼容 JSON 字符串并按结构比较', () => {
    const tableAttribute = {
      attr_name: '磁盘',
      attr_type: 'table',
      option: [
        {
          column_id: 'name',
          column_name: '名称',
          order: 1,
        },
        {
          column_id: 'size',
          column_name: '容量',
          order: 2,
        },
      ],
    };
    const rows = buildChangeRecordDiffRows(
      {
        label: 'instance',
        before_data: {
          disks: '[{"name":"C:","size":100}]',
        },
        after_data: {
          disks: [{ size: 100, name: 'C:' }],
        },
      },
      {
        disks: [{ name: 'C:', size: 100 }],
      },
      { disks: tableAttribute }
    );

    expect(rows[0].before).toBe('名称：C:；容量：100');
    expect(rows[0].changed).toBe(false);
    expect(rows[0].currentDiff).toBe(false);
  });

  it('多行表格一行展示一条记录', () => {
    const rows = buildChangeRecordDiffRows(
      {
        label: 'instance',
        before_data: {},
        after_data: {
          disks: [
            { name: 'C:', size: 100 },
            { name: 'D:', size: 200 },
          ],
        },
      },
      {},
      {
        disks: {
          attr_name: '磁盘',
          attr_type: 'table',
          option: [
            { column_id: 'name', column_name: '名称', order: 1 },
            { column_id: 'size', column_name: '容量', order: 2 },
          ],
        },
      }
    );

    expect(rows[0].after).toBe(
      '名称：C:；容量：100\n名称：D:；容量：200'
    );
  });
});
