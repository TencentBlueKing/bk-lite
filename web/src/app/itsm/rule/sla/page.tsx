'use client';

import { Button, Input, InputNumber, Select, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';

interface PolicyItem {
  id: number;
  name: string;
  target: string;
  minutes: number;
  category: string;
  is_enabled: boolean;
}

interface CalendarItem {
  id: number;
  name: string;
}

const CATEGORIES = [
  { value: 'sla', label: 'SLA' },
  { value: 'slo', label: 'SLO' },
  { value: 'ola', label: 'OLA' },
  { value: 'uc', label: 'UC' },
];

export default function SlaRulePage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [policies, setPolicies] = useState<PolicyItem[]>([]);
  const [calendars, setCalendars] = useState<CalendarItem[]>([]);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [category, setCategory] = useState('sla');
  const [target, setTarget] = useState('response');
  const [minutes, setMinutes] = useState(60);
  const [calendarId, setCalendarId] = useState<number>();

  const load = useCallback(async () => {
    const data = await api.listSla() as { policies?: PolicyItem[]; calendars?: CalendarItem[] };
    setPolicies(data.policies || []);
    setCalendars(data.calendars || []);
  }, [api.listSla]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const save = async () => {
    if (!name.trim() || !calendarId) {
      message.warning(t('itsm.rule.needSla'));
      return;
    }
    await api.saveSla({ kind: 'policy', name: name.trim(), category, target, minutes, calendar_id: calendarId });
    setOpen(false);
    setName('');
    await load();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.rule.sla')}</div>
        <Button type="primary" onClick={() => setOpen(true)}>{t('itsm.rule.newPolicy')}</Button>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <CustomTable
          rowKey="id"
          dataSource={policies}
          locale={{ emptyText: t('itsm.rule.emptySla') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name' },
            { title: t('itsm.rule.category'), dataIndex: 'category', key: 'category', render: (value: string, item: PolicyItem) => (
              <Select className="w-24" size="small" value={value || 'sla'} options={CATEGORIES} onChange={(next) => { void api.saveSla({ policy_id: item.id, category: next }).then(load); }} />
            ) },
            { title: t('itsm.rule.target'), dataIndex: 'target', key: 'target', render: (value: string) => value === 'resolve' ? t('itsm.ticket.resolveDue') : t('itsm.ticket.responseDue') },
            { title: t('itsm.rule.minutes'), dataIndex: 'minutes', key: 'minutes' },
            { title: t('itsm.admin.state'), dataIndex: 'is_enabled', key: 'is_enabled', render: (value: boolean, item: PolicyItem) => (
              <Button size="small" onClick={() => { void api.saveSla({ policy_id: item.id, is_enabled: !value }).then(load); }}>{value ? t('itsm.admin.disable') : t('itsm.admin.enable')}</Button>
            ) },
          ]}
        />
      </div>
      <OperateModal title={t('itsm.rule.newPolicy')} open={open} onCancel={() => setOpen(false)} onOk={() => { void save(); }}>
        <div className="flex flex-col gap-3 text-sm">
          <FieldRow label={t('itsm.portal.name')}>
            <Input placeholder={t('itsm.portal.name')} value={name} onChange={(event) => setName(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.rule.category')}>
            <Select className="w-full" value={category} options={CATEGORIES} onChange={setCategory} />
          </FieldRow>
          <FieldRow label={t('itsm.rule.target')}>
            <Select className="w-full" value={target} options={[{ value: 'response', label: t('itsm.ticket.responseDue') }, { value: 'resolve', label: t('itsm.ticket.resolveDue') }]} onChange={setTarget} />
          </FieldRow>
          <FieldRow label={t('itsm.rule.minutes')}>
            <InputNumber className="w-full" min={1} value={minutes} onChange={(value) => setMinutes(value || 1)} />
          </FieldRow>
          <FieldRow label={t('itsm.rule.pickCalendar')}>
            <Select className="w-full" placeholder={t('itsm.rule.pickCalendar')} value={calendarId} options={calendars.map((item) => ({ value: item.id, label: item.name }))} onChange={setCalendarId} />
          </FieldRow>
        </div>
      </OperateModal>
    </div>
  );
}
