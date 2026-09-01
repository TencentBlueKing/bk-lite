import { describe, expect, it } from 'vitest';

import { buildChangeRecordDiffRows } from '../changeRecordDiff';

describe('buildChangeRecordDiffRows', () => {
  it('优先使用变更发生时的属性定义快照', () => {
    const [row] = buildChangeRecordDiffRows(
      {
        label: 'instance',
        before_data: { network_cards: [{ mac: '00:11', ip: '10.0.0.1' }] },
        after_data: { network_cards: [{ mac: '00:11', ip: '10.0.0.2' }] },
        attribute_snapshot: {
          version: 1,
          attributes: {
            network_cards: {
              attr_id: 'network_cards',
              attr_name: '历史网卡名称',
              attr_type: 'table',
              columns: [
                { column_id: 'mac', column_name: '历史 MAC', column_type: 'str', order: 1, is_row_key: true },
                { column_id: 'ip', column_name: '历史 IP', column_type: 'str', order: 2 },
              ],
            },
          },
        },
      },
      { network_cards: [{ mac: '00:11', ip: '10.0.0.2' }] },
      {
        network_cards: {
          attr_name: '当前已改名',
          attr_type: 'table',
          option: [{ column_id: 'renamed', column_name: '当前新列', order: 1 }],
        },
      }
    );

    expect(row.attr).toBe('历史网卡名称');
    expect(row.table?.matchMode).toBe('row-key');
    expect(row.table?.rows[0].cells.map((cell) => cell.columnName)).toEqual([
      '历史 MAC',
      '历史 IP',
    ]);
  });

  it('按行号返回表格字段的单元格级差异', () => {
    const rows = buildChangeRecordDiffRows(
      {
        label: 'instance',
        before_data: {
          network_cards: [{ name: 'eth0', ip: '10.0.0.1' }],
        },
        after_data: {
          network_cards: [{ name: 'eth0', ip: '10.0.0.2' }],
        },
      },
      {
        network_cards: [{ name: 'eth0', ip: '10.0.0.3' }],
      },
      {
        network_cards: {
          attr_name: '网卡',
          attr_type: 'table',
          option: [
            { column_id: 'name', column_name: '名称', order: 1 },
            { column_id: 'ip', column_name: 'IP 地址', order: 2 },
          ],
        },
      }
    );

    expect(rows[0].kind).toBe('table');
    expect(rows[0].table?.matchMode).toBe('position');
    expect(rows[0].table?.summary).toEqual({
      addedRows: 0,
      removedRows: 0,
      modifiedRows: 1,
      changedCells: 1,
    });
    expect(rows[0].table?.rows[0]).toMatchObject({
      status: 'modified',
      beforeIndex: 0,
      afterIndex: 0,
      currentIndex: 0,
    });
    expect(rows[0].table?.rows[0].cells).toEqual([
      {
        columnId: 'name',
        columnName: '名称',
        before: 'eth0',
        after: 'eth0',
        current: 'eth0',
        changed: false,
        currentDiff: false,
      },
      {
        columnId: 'ip',
        columnName: 'IP 地址',
        before: '10.0.0.1',
        after: '10.0.0.2',
        current: '10.0.0.3',
        changed: true,
        currentDiff: true,
      },
    ]);
  });

  it('通过公共前后缀识别中间新增行而不制造级联修改', () => {
    const attr = {
      attr_name: '磁盘',
      attr_type: 'table',
      option: [
        { column_id: 'name', column_name: '名称', order: 1 },
        { column_id: 'size', column_name: '容量', order: 2 },
      ],
    };
    const before = [
      { name: 'C:', size: 100 },
      { name: 'D:', size: 200 },
    ];
    const after = [
      { name: 'C:', size: 100 },
      { name: 'E:', size: 300 },
      { name: 'D:', size: 200 },
    ];

    const [row] = buildChangeRecordDiffRows(
      { label: 'instance', before_data: { disks: before }, after_data: { disks: after } },
      { disks: after },
      { disks: attr }
    );

    expect(row.table?.rows.map((item) => item.status)).toEqual([
      'unchanged',
      'added',
      'unchanged',
    ]);
    expect(row.table?.rows[1]).toMatchObject({
      beforeIndex: undefined,
      afterIndex: 1,
      currentIndex: 1,
    });
    expect(row.table?.summary).toEqual({
      addedRows: 1,
      removedRows: 0,
      modifiedRows: 0,
      changedCells: 2,
    });
  });

  it('按行标识精确匹配重排后的行和变化单元格', () => {
    const before = [
      { name: 'eth0', ip: '10.0.0.1' },
      { name: 'eth1', ip: '10.0.0.2' },
    ];
    const after = [
      { name: 'eth1', ip: '10.0.0.3' },
      { name: 'eth0', ip: '10.0.0.1' },
    ];
    const [row] = buildChangeRecordDiffRows(
      {
        label: 'instance',
        before_data: { network_cards: before },
        after_data: { network_cards: after },
      },
      { network_cards: after },
      {
        network_cards: {
          attr_name: '网卡',
          attr_type: 'table',
          option: [
            {
              column_id: 'name',
              column_name: '名称',
              order: 1,
              is_row_key: true,
            },
            { column_id: 'ip', column_name: 'IP 地址', order: 2 },
          ],
        },
      }
    );

    expect(row.table?.matchMode).toBe('row-key');
    expect(row.table?.rowKeyColumnId).toBe('name');
    expect(row.table?.rows).toHaveLength(2);
    expect(row.table?.rows[0]).toMatchObject({
      beforeIndex: 1,
      afterIndex: 0,
      currentIndex: 0,
      status: 'modified',
    });
    expect(row.table?.rows[0].cells.find((cell) => cell.columnId === 'ip')).toMatchObject({
      before: '10.0.0.2',
      after: '10.0.0.3',
      changed: true,
    });
    expect(row.table?.rows[1]).toMatchObject({
      beforeIndex: 0,
      afterIndex: 1,
      status: 'moved',
    });
    expect(row.table?.summary).toEqual({
      addedRows: 0,
      removedRows: 0,
      modifiedRows: 1,
      changedCells: 1,
    });
  });

  it('行标识重复时安全降级为按位置匹配', () => {
    const [row] = buildChangeRecordDiffRows(
      {
        label: 'instance',
        before_data: { disks: [{ name: 'same', size: 1 }, { name: 'same', size: 2 }] },
        after_data: { disks: [{ name: 'same', size: 1 }, { name: 'same', size: 3 }] },
      },
      { disks: [{ name: 'same', size: 1 }, { name: 'same', size: 3 }] },
      {
        disks: {
          attr_name: '磁盘',
          attr_type: 'table',
          option: [
            { column_id: 'name', column_name: '名称', order: 1, is_row_key: true },
            { column_id: 'size', column_name: '容量', order: 2 },
          ],
        },
      }
    );

    expect(row.table?.matchMode).toBe('position');
    expect(row.table?.fallbackReason).toBe('duplicate-row-key');
    expect(row.table?.summary.modifiedRows).toBe(1);
  });

  it('无行标识时识别纯重排而不误报单元格修改', () => {
    const before = [{ name: 'C:', size: 100 }, { name: 'D:', size: 200 }];
    const after = [...before].reverse();
    const [row] = buildChangeRecordDiffRows(
      { label: 'instance', before_data: { disks: before }, after_data: { disks: after } },
      { disks: after },
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

    expect(row.table?.rows.map((item) => item.status)).toEqual(['moved', 'moved']);
    expect(row.table?.summary.changedCells).toBe(0);
  });

  it('按位置匹配时保留历史记录之后新增的当前态行', () => {
    const history = [{ name: 'C:', size: 100 }];
    const [row] = buildChangeRecordDiffRows(
      { label: 'instance', before_data: { disks: history }, after_data: { disks: history } },
      { disks: [...history, { name: 'D:', size: 200 }] },
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

    expect(row.table?.rows).toHaveLength(2);
    expect(row.table?.rows[1]).toMatchObject({
      beforeIndex: undefined,
      afterIndex: undefined,
      currentIndex: 1,
      status: 'unchanged',
    });
    expect(row.table?.rows[1].cells.every((cell) => cell.currentDiff)).toBe(true);
  });

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

  it('将缺失、null 和空字符串统一按空单元格比较', () => {
    const [row] = buildChangeRecordDiffRows(
      {
        label: 'instance',
        before_data: { interfaces: [{ name: 'eth0' }] },
        after_data: { interfaces: [{ name: 'eth0', note: '' }] },
      },
      { interfaces: [{ name: 'eth0', note: null }] },
      {
        interfaces: {
          attr_name: '网卡',
          attr_type: 'table',
          option: [
            { column_id: 'name', column_name: '名称', order: 1 },
            { column_id: 'note', column_name: '备注', order: 2 },
          ],
        },
      }
    );

    expect(row.changed).toBe(false);
    expect(row.currentDiff).toBe(false);
    expect(row.table?.summary).toEqual({
      addedRows: 0,
      removedRows: 0,
      modifiedRows: 0,
      changedCells: 0,
    });
    expect(row.table?.rows[0].cells[1]).toMatchObject({
      before: '--',
      after: '--',
      current: '--',
      changed: false,
      currentDiff: false,
    });
  });

  it('字段定义已删除的旧表格记录仍降级为单元格差异', () => {
    const [row] = buildChangeRecordDiffRows(
      {
        label: 'instance',
        before_data: { legacy_table: [{ name: 'C:', size: 100 }] },
        after_data: { legacy_table: [{ name: 'C:', size: 200 }] },
      },
      {},
      {}
    );

    expect(row.attr).toBe('legacy_table');
    expect(row.kind).toBe('table');
    expect(row.table?.matchMode).toBe('position');
    expect(row.table?.rows[0].cells.map((cell) => cell.columnId)).toEqual([
      'name',
      'size',
    ]);
    expect(row.table?.summary).toEqual({
      addedRows: 0,
      removedRows: 0,
      modifiedRows: 1,
      changedCells: 1,
    });
  });
});
