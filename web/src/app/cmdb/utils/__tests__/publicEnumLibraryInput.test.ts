import { describe, expect, it } from 'vitest';

import {
  collectPublicEnumOptionsForSave,
  trimPublicEnumOptions,
  trimPublicEnumText,
} from '../publicEnumLibraryInput';

describe('公共选项库录入去空格', () => {
  it('去掉文本前后空格，中间空格保留', () => {
    expect(trimPublicEnumText('  企业系统部  ')).toBe('企业系统部');
    expect(trimPublicEnumText('Core Technology')).toBe('Core Technology');
    expect(trimPublicEnumText('   ')).toBe('');
  });

  it('选项 ID 和名称一并去掉前后空格', () => {
    expect(
      trimPublicEnumOptions([
        { id: '  Enterprise_Systems  ', name: '  企业系统部  ' },
        { id: 'Infrastructure', name: '基建及安全部' },
      ])
    ).toEqual([
      { id: 'Enterprise_Systems', name: '企业系统部' },
      { id: 'Infrastructure', name: '基建及安全部' },
    ]);
  });

  it('保存时丢弃去空格后为空的行', () => {
    expect(
      collectPublicEnumOptionsForSave([
        { id: '  foo  ', name: '  名称  ' },
        { id: '   ', name: '空ID' },
        { id: 'bar', name: '   ' },
        { id: '', name: '' },
      ])
    ).toEqual([{ id: 'foo', name: '名称' }]);
  });
});
