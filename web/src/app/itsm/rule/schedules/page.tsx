'use client';

import { ItsmListEntry } from '@/app/itsm/components/list-entry';

import { ItsmRowActions, ItsmListToolbar, ItsmCreateButton } from '@/app/itsm/components/list-controls';

import { DatePicker, Input, Radio, Select, Switch, message } from 'antd';
import dayjs from 'dayjs';
import { useCallback, useEffect, useState } from 'react';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';

interface ScheduleItem {
  id: number;
  name: string;
  cron: string;
  action: string;
  is_enabled: boolean;
}

interface WorkflowItem {
  id: number;
  name: string;
}

interface ActionConfig {
  task: 'create_ticket' | 'remind';
  workflow_id?: number;
  notify: boolean;
  mode: 'once' | 'cron';
  once_at?: string;
}

const parseAction = (raw: string): ActionConfig => {
  try {
    const data = JSON.parse(raw) as ActionConfig;
    if (data.task) {
      return data;
    }
  } catch {
    // 旧数据是 create_ticket:id
  }
  const workflowId = Number(raw.split(':')[1]);
  return { task: 'create_ticket', workflow_id: Number.isFinite(workflowId) ? workflowId : undefined, notify: false, mode: 'cron' };
};

export default function Page() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [keyword, setKeyword] = useState('');
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ScheduleItem | null>(null);
  const [name, setName] = useState('');
  const [mode, setMode] = useState<'once' | 'cron'>('cron');
  const [cron, setCron] = useState('0 9 * * 1-5');
  const [onceAt, setOnceAt] = useState('');
  const [task, setTask] = useState<'create_ticket' | 'remind'>('create_ticket');
  const [workflowId, setWorkflowId] = useState<number>();
  const [notify, setNotify] = useState(false);

  const load = useCallback(async () => {
    const [scheduleData, workflowData] = await Promise.all([
      api.listResources('schedules') as Promise<{ items?: ScheduleItem[] }>,
      api.listWorkflows() as Promise<{ items?: WorkflowItem[] }>,
    ]);
    setItems(scheduleData.items || []);
    setWorkflows(workflowData.items || []);
  }, [api.listResources, api.listWorkflows]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const start = (item?: ScheduleItem) => {
    const config = item ? parseAction(item.action) : null;
    setEditing(item || null);
    setName(item?.name || '');
    setMode(config?.mode || (item?.cron ? 'cron' : 'once'));
    setCron(item?.cron || '0 9 * * 1-5');
    setOnceAt(config?.once_at || '');
    setTask(config?.task || 'create_ticket');
    setWorkflowId(config?.workflow_id);
    setNotify(Boolean(config?.notify));
    setOpen(true);
  };

  const save = async () => {
    if (!workflowId) {
      message.warning(t('itsm.rule.needWorkflow'));
      return;
    }
    const body = {
      name,
      cron: mode === 'cron' ? cron : '',
      action: JSON.stringify({ task, workflow_id: workflowId, notify, mode, once_at: onceAt }),
    };
    if (editing) {
      await api.updateResource('schedules', editing.id, body);
    } else {
      await api.createResource('schedules', body);
    }
    setOpen(false);
    message.success(editing ? t('itsm.portal.saved') : t('itsm.portal.created'));
    await load();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <ItsmListToolbar search={{ value: keyword, onChange: setKeyword, placeholder: '搜索名称或标识' }} actions={<ItsmCreateButton onClick={() => start()} />} />
        <CustomTable queryKey={keyword}
          rowKey="id"
          dataSource={items.filter(item => `${item.name}`.toLowerCase().includes(keyword.trim().toLowerCase()))}
          locale={{ emptyText: t('itsm.rule.emptySchedule') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name', render: (value: string, item: ScheduleItem) => <ItsmListEntry onClick={() => start(item)}>{value}</ItsmListEntry> },
            { title: t('itsm.rule.mode'), key: 'mode', render: (_value: unknown, item: ScheduleItem) => parseAction(item.action).mode === 'once' ? t('itsm.rule.once') : t('itsm.rule.cron') },
            { title: t('itsm.rule.period'), dataIndex: 'cron', key: 'cron', render: (value: string) => value || '—' },
            { title: t('itsm.rule.taskType'), key: 'task', render: (_value: unknown, item: ScheduleItem) => parseAction(item.action).task === 'remind' ? t('itsm.rule.remind') : t('itsm.rule.createTicket') },
            { title: t('itsm.rule.notifyCol'), key: 'notify', render: (_value: unknown, item: ScheduleItem) => parseAction(item.action).notify ? t('itsm.rule.send') : t('itsm.rule.noSend') },
            {
              title: t('itsm.admin.enable'),
              dataIndex: 'is_enabled',
              key: 'is_enabled',
              render: (value: boolean, item: ScheduleItem) => (
                <Switch checked={value} onChange={(checked) => { void api.updateResource('schedules', item.id, { is_enabled: checked }).then(load); }} />
              ),
            },
            { fixed: 'right' as const, width: 120,
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: ScheduleItem) => <ItsmRowActions items={[{key: 'action-0', label: t('itsm.common.edit'), kind: 'edit' as const, onClick: () => start(item)},
                {key: 'action-1', label: t('itsm.common.delete'), kind: 'delete' as const, danger: true, confirm: {title: t('itsm.rule.deleteSchedule'), content: undefined }, onClick: () => { void api.deleteResource('schedules', item.id).then(load); }}]} />,
            },
          ]}
        />
      </div>
      <OperateModal title={editing ? t('itsm.rule.editSchedule') : t('itsm.rule.newSchedule')} open={open} onCancel={() => setOpen(false)} onOk={() => { void save(); }}>
        <div className="flex flex-col gap-3 text-sm">
          <FieldRow label={t('itsm.portal.name')}>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.rule.mode')}>
            <Radio.Group value={mode} onChange={(event) => setMode(event.target.value)}>
              <Radio value="once">{t('itsm.rule.once')}</Radio>
              <Radio value="cron">{t('itsm.rule.cron')}</Radio>
            </Radio.Group>
          </FieldRow>
          {mode === 'once' ? (
            <FieldRow label={t('itsm.rule.once')}>
              <DatePicker showTime className="w-full" value={onceAt ? dayjs(onceAt) : null} onChange={(value) => setOnceAt(value ? value.toISOString() : '')} />
            </FieldRow>
          ) : (
            <FieldRow label={t('itsm.rule.period')}>
              <Input placeholder={t('itsm.rule.cronHint')} value={cron} onChange={(event) => setCron(event.target.value)} />
            </FieldRow>
          )}
          <FieldRow label={t('itsm.rule.taskType')}>
            <Select className="w-full" value={task} options={[{ value: 'create_ticket', label: t('itsm.rule.createTicket') }, { value: 'remind', label: t('itsm.rule.remind') }]} onChange={setTask} />
          </FieldRow>
          <FieldRow label={t('itsm.ticket.flow')}>
            <Select className="w-full" placeholder={t('itsm.rule.pickWorkflow')} value={workflowId} options={workflows.map((item) => ({ value: item.id, label: item.name }))} onChange={setWorkflowId} />
          </FieldRow>
          <FieldRow label={t('itsm.rule.notifyCol')}>
            <Switch checked={notify} onChange={setNotify} />
          </FieldRow>
        </div>
      </OperateModal>
    </div>
  );
}
