'use client';

import { ItsmListEntry } from '@/app/itsm/components/list-entry';

import { ItsmRowActions, ItsmListToolbar, ItsmCreateButton } from '@/app/itsm/components/list-controls';

import { Checkbox, Input, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { ItsmModal as OperateModal } from '@/app/itsm/components/interaction-surfaces';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';

interface CalendarItem {
  id: number;
  name: string;
  work_days: number[];
  work_start: string;
  work_end: string;
  timezone: string;
}

const DAY_VALUES = [1, 2, 3, 4, 5, 6, 7];

export default function CalendarsPage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [keyword, setKeyword] = useState('');
  const daysOptions = DAY_VALUES.map((value) => ({ value, label: t(`itsm.rule.day${value}`) }));
  const [items, setItems] = useState<CalendarItem[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<CalendarItem | null>(null);
  const [name, setName] = useState('');
  const [days, setDays] = useState<number[]>([1, 2, 3, 4, 5]);
  const [start, setStart] = useState('09:00');
  const [zone, setZone] = useState('Asia/Shanghai');
  const [end, setEnd] = useState('18:00');

  const load = useCallback(async () => {
    const data = await api.listSla() as { calendars?: CalendarItem[] };
    setItems(data.calendars || []);
  }, [api.listSla]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const startEdit = (item?: CalendarItem) => {
    setEditing(item || null);
    setName(item?.name || '');
    setDays(item?.work_days?.length ? item.work_days : [1, 2, 3, 4, 5]);
    setStart(item?.work_start || '09:00');
    setZone(item?.timezone || 'Asia/Shanghai');
    setEnd(item?.work_end || '18:00');
    setOpen(true);
  };

  const save = async () => {
    if (!name.trim()) {
      message.warning(t('itsm.rule.needCalendar'));
      return;
    }
    await api.saveSla({ kind: 'calendar', id: editing?.id, name: name.trim(), work_days: days, work_start: start, work_end: end, timezone: zone.trim() });
    setOpen(false);
    await load();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <ItsmListToolbar search={{ value: keyword, onChange: setKeyword, placeholder: '搜索名称或标识' }} actions={<ItsmCreateButton onClick={() => startEdit()} />} />
        <CustomTable queryKey={keyword}
          rowKey="id"
          dataSource={items.filter(item => `${item.name}`.toLowerCase().includes(keyword.trim().toLowerCase()))}
          locale={{ emptyText: t('itsm.rule.emptyCalendar') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name', render: (value: string, item: CalendarItem) => <ItsmListEntry onClick={() => startEdit(item)}>{value}</ItsmListEntry> },
            { title: t('itsm.rule.workdays'), dataIndex: 'work_days', key: 'work_days', render: (value: number[]) => (value || []).map((day) => daysOptions.find((item) => item.value === day)?.label).filter(Boolean).join('、') },
            { title: t('itsm.rule.range'), key: 'range', render: (_value: unknown, item: CalendarItem) => `${item.work_start}-${item.work_end}` },
            { title: '时区', dataIndex: 'timezone', key: 'timezone' },
            { fixed: 'right' as const, width: 120, title: t('itsm.ticket.action'), key: 'actions', render: (_value: unknown, item: CalendarItem) => <ItsmRowActions items={[{key: 'action-0', label: t('itsm.common.edit'), kind: 'edit' as const, onClick: () => startEdit(item)}]} /> },
          ]}
        />
      </div>
      <OperateModal formValue={{name,days,start,end,zone}} title={editing ? t('itsm.rule.editCalendar') : t('itsm.rule.newCalendar')} open={open} onCancel={() => setOpen(false)} onOk={save}>
        <div className="flex flex-col gap-3 text-sm">
          <FieldRow label={t('itsm.portal.name')}>
            <Input placeholder={t('itsm.rule.windowName')} value={name} onChange={(event) => setName(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.rule.workdays')} align="start">
            <Checkbox.Group options={daysOptions} value={days} onChange={(value) => setDays(value as number[])} />
          </FieldRow>
          <FieldRow label="时区"><Input aria-label="服务窗口时区" placeholder="例如 Asia/Shanghai" value={zone} onChange={event => setZone(event.target.value)} /></FieldRow>
          <FieldRow label={t('itsm.rule.range')}>
            <div className="flex gap-2">
              <Input placeholder={t('itsm.rule.start')} value={start} onChange={(event) => setStart(event.target.value)} />
              <Input placeholder={t('itsm.rule.end')} value={end} onChange={(event) => setEnd(event.target.value)} />
            </div>
          </FieldRow>
        </div>
      </OperateModal>
    </div>
  );
}
