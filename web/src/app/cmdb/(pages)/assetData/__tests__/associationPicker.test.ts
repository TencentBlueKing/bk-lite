import { sortAssociationPickerOptions } from '../associationPicker';

describe('sortAssociationPickerOptions', () => {
  it('把运行于主机排在关联依赖前面，关联按名称排序', () => {
    const sorted = sortAssociationPickerOptions([
      { id: 'redis', asst_id: 'connect', name: '应用-关联-Redis' },
      { id: 'host', asst_id: 'run', name: '应用-运行于-主机' },
      { id: 'mysql', asst_id: 'connect', name: '应用-关联-MySQL' },
    ]);
    expect(sorted.map((item) => item.name)).toEqual([
      '应用-运行于-主机',
      '应用-关联-MySQL',
      '应用-关联-Redis',
    ]);
  });
});
