import { describe, expect, it } from 'vitest';

import { buildHostPickerQuery, formatHostOsType } from '../hostPickerFilter';

describe('选择主机筛选', () => {
  it('在已有云区域条件上追加实例名、管理 IP 和操作系统', () => {
    expect(
      buildHostPickerQuery(
        [{ field: 'cloud', type: 'int=', value: 2 }],
        { instName: ' win-app ', ip: '10.1.8', osType: '2' }
      )
    ).toEqual([
      { field: 'cloud', type: 'int=', value: 2 },
      { field: 'inst_name', type: 'str*', value: 'win-app' },
      { field: 'ip_addr', type: 'str*', value: '10.1.8' },
      { field: 'os_type', type: 'list_any[]', value: ['2'] },
    ]);
  });

  it('空白条件不生成查询', () => {
    expect(buildHostPickerQuery([], { instName: '  ', ip: '', osType: undefined })).toEqual([]);
  });

  it('操作系统展示枚举名称', () => {
    expect(formatHostOsType('2')).toBe('Windows');
    expect(formatHostOsType('Linux')).toBe('Linux');
    expect(formatHostOsType('')).toBe('--');
    expect(formatHostOsType('Windows Server')).toBe('Windows Server');
  });
});
