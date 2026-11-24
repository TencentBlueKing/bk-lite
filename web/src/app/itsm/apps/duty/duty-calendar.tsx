'use client';

import { LeftOutlined, PlusOutlined, RightOutlined } from '@ant-design/icons';
import { Button, Calendar, DatePicker, Empty, Spin, Tag } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { ItsmListEntry } from '../../components/list-entry';

export interface DutyShift {
  id: number;
  name: string;
  day: string | null;
  members: string[];
}

export function memberNames(members: unknown): string[] {
  return Array.isArray(members) ? members.filter(member => typeof member === 'string') : [];
}

interface DutyCalendarProps {
  date: Dayjs;
  onChange: (date: Dayjs) => void;
  rows: DutyShift[];
  loading: boolean;
  create?: () => void;
  edit?: (row: DutyShift) => void;
}

export function DutyCalendar({ date, onChange, rows, loading, create, edit }: DutyCalendarProps) {
  const byDate = new Map<string, DutyShift[]>();
  for (const shift of rows) {
    if (!shift.day) continue;
    const shifts = byDate.get(shift.day) ?? [];
    shifts.push(shift);
    byDate.set(shift.day, shifts);
  }

  const selectedDate = date.format('YYYY-MM-DD');
  const selectedShifts = byDate.get(selectedDate) ?? [];
  const detailTitle = `${selectedDate} 值班`;

  return <Spin spinning={loading}>
    <div className="grid min-w-0 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_16rem]">
      <Calendar value={date} mode="month" onChange={onChange}
        headerRender={() => <div className="mb-2 flex flex-wrap items-center gap-1">
          <Button aria-label="上个月" icon={<LeftOutlined />} onClick={() => onChange(date.subtract(1, 'month'))} />
          <DatePicker picker="month" aria-label="选择排班月份" value={date} allowClear={false}
            format="YYYY年M月" onChange={value => value && onChange(value)} />
          <Button aria-label="下个月" icon={<RightOutlined />} onClick={() => onChange(date.add(1, 'month'))} />
          <Button onClick={() => onChange(dayjs())}>今天</Button>
        </div>}
        fullCellRender={day => {
          const key = day.format('YYYY-MM-DD');
          const shifts = byDate.get(key) ?? [];
          const selected = key === selectedDate;
          const isInMonth = day.isSame(date, 'month');
          return <button type="button" aria-label={`${key}，${shifts.length} 个排班`} aria-pressed={selected}
            className={`flex h-20 w-full min-w-0 flex-col overflow-hidden rounded border-t px-1 py-1 text-left hover:bg-[var(--color-fill-2)] focus-visible:outline focus-visible:outline-[var(--color-primary)] sm:px-2 ${selected
              ? 'border-[var(--color-primary)] bg-[var(--color-fill-2)] text-[var(--color-primary)]'
              : 'border-[var(--color-border)]'} ${isInMonth ? '' : 'text-[var(--color-text-3)]'}`}
            onClick={event => {
              event.stopPropagation();
              onChange(day);
            }}>
            <span className="text-xs tabular-nums">{day.date()}</span>
            {shifts.slice(0, 2).map(shift => <span key={shift.id} title={shift.name}
              className="w-full truncate text-xs text-[var(--color-text-2)]">{shift.name}</span>)}
            {shifts.length > 2 && <span className="text-xs text-[var(--color-text-3)]">+{shifts.length - 2}</span>}
          </button>;
        }} />
      <section aria-label={detailTitle} className="min-w-0 rounded-lg border border-[var(--color-border)] p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="m-0 text-sm font-semibold text-[var(--color-text-1)]">{detailTitle}</h3>
          {create && <Button size="small" icon={<PlusOutlined aria-hidden />} onClick={create}>新建当日排班</Button>}
        </div>
        {selectedShifts.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当日暂无排班" />
        : <ul className="mb-0 mt-3 list-none divide-y divide-[var(--color-border)] p-0">
          {selectedShifts.map(shift => <li key={shift.id} className="space-y-2 py-2">
            {edit ? <ItsmListEntry onClick={() => edit(shift)}>{shift.name}</ItsmListEntry> : <div>{shift.name}</div>}
            <div className="flex flex-wrap gap-y-1">
              {memberNames(shift.members).map(member => <Tag key={member}>{member}</Tag>)}
            </div>
          </li>)}
        </ul>}
      </section>
    </div>
  </Spin>;
}
