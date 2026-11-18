'use client';

import { ItsmListEntry } from '@/app/itsm/components/list-entry';

import { ItsmRowActions, ItsmListToolbar, ItsmCreateButton } from '@/app/itsm/components/list-controls';

import { Input, Select, Switch, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { ItsmDrawer as OperateModal } from '@/app/itsm/components/interaction-surfaces';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';

interface TriggerItem {
  id: number;
  name: string;
  event: string;
  action: string;
  config: { when?: { field?: string; op?: string; value?: string }; response?: string };
  is_enabled: boolean;
}

const EVENTS = [
  'ticket_create',
  'ticket_update',
  'ticket_suspend',
  'ticket_recovery',
  'ticket_back',
  'ticket_withdraw',
  'ticket_end',
  'ticket_finish',
  'ticket_close',
  'ticket_terminate',
  'ticket_urging',
  'activity_into',
];

const ACTIONS = [
  { value: 'tag', labelKey: 'itsm.rule.tag' },
  { value: 'notice', labelKey: 'itsm.rule.notice' },
  { value: 'status', labelKey: 'itsm.rule.changeStatus' },
];

export default function Page() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [keyword, setKeyword] = useState('');
  const [items, setItems] = useState<TriggerItem[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<TriggerItem | null>(null);
  const [name, setName] = useState('');
  const [event, setEvent] = useState('ticket_create');
  const [action, setAction] = useState('notice');
  const [field, setField] = useState('');
  const [op, setOp] = useState('eq');
  const [value, setValue] = useState('');
  const [response, setResponse] = useState('');

  const load = useCallback(async () => {
    const data = await api.listResources('triggers') as { items?: TriggerItem[] };
    setItems(data.items || []);
  }, [api.listResources]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const start = (item?: TriggerItem) => {
    setEditing(item || null);
    setName(item?.name || '');
    setEvent(item?.event || 'ticket_create');
    setAction(item?.action || 'notice');
    setField(item?.config?.when?.field || '');
    setOp(item?.config?.when?.op || 'eq');
    setValue(item?.config?.when?.value || '');
    setResponse(item?.config?.response || '');
    setOpen(true);
  };

  const save = async () => {
    const body = { name, event, action, config: { when: { field, op, value }, response } };
    if (editing) {
      await api.updateResource('triggers', editing.id, body);
    } else {
      await api.createResource('triggers', body);
    }
    setOpen(false);
    message.success(editing ? t('itsm.portal.saved') : t('itsm.portal.created'));
    await load();
  };

  const eventOptions = EVENTS.map((value) => ({ value, label: t(`itsm.rule.${value}`) }));
  const actionOptions = ACTIONS.map((item) => ({ value: item.value, label: t(item.labelKey) }));

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <ItsmListToolbar search={{ value: keyword, onChange: setKeyword, placeholder: '搜索名称或标识' }} actions={<ItsmCreateButton onClick={() => start()} />} />
        <CustomTable queryKey={keyword}
          rowKey="id"
          dataSource={items.filter(item => `${item.name}`.toLowerCase().includes(keyword.trim().toLowerCase()))}
          locale={{ emptyText: t('itsm.rule.emptyTrigger') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name', render: (value: string, item: TriggerItem) => <ItsmListEntry onClick={() => start(item)}>{value}</ItsmListEntry> },
            { title: t('itsm.rule.event'), dataIndex: 'event', key: 'event', render: (value: string) => eventOptions.find((item) => item.value === value)?.label || value },
            { title: t('itsm.rule.response'), dataIndex: 'action', key: 'action', render: (value: string) => actionOptions.find((item) => item.value === value)?.label || value },
            {
              title: t('itsm.admin.enable'),
              dataIndex: 'is_enabled',
              key: 'is_enabled',
              render: (value: boolean, item: TriggerItem) => (
                <Switch checked={value} onChange={(checked) => { void api.updateResource('triggers', item.id, { is_enabled: checked }).then(load); }} />
              ),
            },
            { fixed: 'right' as const, width: 120,
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: TriggerItem) => <ItsmRowActions items={[{key: 'action-0', label: t('itsm.common.edit'), kind: 'edit' as const, onClick: () => start(item)},
                {key: 'action-1', label: t('itsm.common.delete'), kind: 'delete' as const, danger: true, confirm: {title: t('itsm.rule.deleteTrigger'), content: undefined }, onClick: () => { void api.deleteResource('triggers', item.id).then(load); }}]} />,
            },
          ]}
        />
      </div>
      <OperateModal formValue={{name,event,action,field,op,value,response}} title={editing ? t('itsm.rule.editTrigger') : t('itsm.rule.newTrigger')} open={open} onCancel={() => setOpen(false)} onOk={save}>
        <div className="flex flex-col gap-3 text-sm">
          <FieldRow label={t('itsm.portal.name')}>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.rule.event')}>
            <Select className="w-full" value={event} options={eventOptions} onChange={setEvent} />
          </FieldRow>
          <FieldRow label={t('itsm.rule.when')}>
            <div className="flex gap-2">
              <Input placeholder={t('itsm.rule.field')} value={field} onChange={(event) => setField(event.target.value)} />
              <Select className="w-28" value={op} options={[{ value: 'eq', label: t('itsm.rule.eq') }, { value: 'contains', label: t('itsm.rule.contains') }]} onChange={setOp} />
              <Input placeholder={t('itsm.rule.value')} value={value} onChange={(event) => setValue(event.target.value)} />
            </div>
          </FieldRow>
          <FieldRow label={t('itsm.rule.response')}>
            <Select className="w-full" value={action} options={actionOptions} onChange={setAction} />
          </FieldRow>
          <FieldRow label={t('itsm.rule.value')}>
            <Input placeholder={t('itsm.rule.responseHint')} value={response} onChange={(event) => setResponse(event.target.value)} />
          </FieldRow>
        </div>
      </OperateModal>
    </div>
  );
}
