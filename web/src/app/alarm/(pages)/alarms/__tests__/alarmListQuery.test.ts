import { expect, it } from 'vitest';
import { withAlarmSearchCondition } from '../alarmListQuery';

const base = { status: 'pending,processing', page: 1 };

it('状态下拉用所选状态覆盖侧栏状态，交给列表接口过滤', () => {
  expect(withAlarmSearchCondition(base, {
    field: 'status',
    type: 'enum',
    value: 'unassigned',
  })).toEqual({ status: 'unassigned', page: 1 });
});

it('清空状态搜索时保留侧栏状态', () => {
  expect(withAlarmSearchCondition(base, {
    field: 'status',
    type: 'enum',
    value: '',
  })).toEqual(base);
});

it('名称搜索仍按字段传给后端', () => {
  expect(withAlarmSearchCondition(base, {
    field: 'title',
    type: 'str',
    value: 'cpu',
  })).toEqual({ ...base, title: 'cpu' });
});
