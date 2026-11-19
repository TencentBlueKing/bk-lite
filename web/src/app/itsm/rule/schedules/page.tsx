'use client';

import { ItsmListEntry } from '@/app/itsm/components/list-entry';

import { ItsmRowActions, ItsmListToolbar, ItsmCreateButton } from '@/app/itsm/components/list-controls';

import { Button, DatePicker, Input, Radio, Select, Switch, message } from 'antd';
import dayjs from 'dayjs';
import { useCallback, useEffect, useState } from 'react';
import { ItsmDrawer as OperateModal } from '@/app/itsm/components/interaction-surfaces';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';
import { ScheduleRunHistory, type ScheduleHistoryTarget } from './run-history';
import { formatTicketTime } from '../../components/ticket-collaboration';

interface ScheduleItem {
  id: number;
  name: string;
  cron: string;
  action: string;
  is_enabled: boolean;
  next_run_at: string | null;
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
  form_data?: Record<string, unknown>;
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
  const [formData, setFormData] = useState('{}');
  const [history, setHistory] = useState<ScheduleHistoryTarget>();
  const [permissions, setPermissions] = useState({ can_add: false, can_edit: false, can_delete: false });

  const load = useCallback(async () => {
    const scheduleData = await api.listResources('schedules') as typeof permissions & { items?: ScheduleItem[] };
    setItems(scheduleData.items || []);
    setPermissions(scheduleData);
  }, [api.listResources]);

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
    setMode(config?.mode || 'cron');
    setCron(item?.cron || '0 9 * * 1-5');
    setOnceAt(config?.once_at || '');
    setTask(config?.task || 'create_ticket');
    setWorkflowId(config?.workflow_id);
    setNotify(Boolean(config?.notify));
    setFormData(JSON.stringify(config?.form_data || {}, null, 2));
    setOpen(true);
  };

  useEffect(() => {
    if (!open || task !== 'create_ticket') return;
    let active = true;
    void api.listTicketWorkflows().then((response) => {
      if (active) setWorkflows((response as { items: WorkflowItem[] }).items);
    }).catch((error: unknown) => {
      if (active) message.error(error instanceof Error ? error.message : '读取可提单流程失败');
    });
    return () => { active = false; };
  }, [open, task, api.listTicketWorkflows]);

  const save = async () => {
    if (task === 'create_ticket' && !workflowId) {
      message.warning(t('itsm.rule.needWorkflow'));
      return;
    }
    let values = {};
    if (task === 'create_ticket') {
      try {
        values = JSON.parse(formData);
        if (!values || Array.isArray(values) || typeof values !== 'object') throw new Error();
      } catch {
        throw new Error('表单参数需填写为 JSON 对象');
      }
    }
    const body = {
      name,
      cron: mode === 'cron' ? cron : '',
      action: JSON.stringify({ task, workflow_id: workflowId, notify, mode, once_at: onceAt, form_data: values }),
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
        <ItsmListToolbar search={{ value: keyword, onChange: setKeyword, placeholder: '搜索任务名称' }} actions={<>
          <Button onClick={() => setHistory({})}>执行记录</Button>
          {permissions.can_add && <ItsmCreateButton onClick={() => start()} />}
        </>} />
        <CustomTable queryKey={keyword}
          rowKey="id"
          dataSource={items.filter(item => `${item.name}`.toLowerCase().includes(keyword.trim().toLowerCase()))}
          locale={{ emptyText: t('itsm.rule.emptySchedule') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name', render: (value: string, item: ScheduleItem) => <ItsmListEntry allowed={permissions.can_edit} onClick={() => start(item)}>{value}</ItsmListEntry> },
            { title: t('itsm.rule.mode'), key: 'mode', render: (_value: unknown, item: ScheduleItem) => parseAction(item.action).mode === 'once' ? t('itsm.rule.once') : t('itsm.rule.cron') },
            { title: t('itsm.rule.period'), dataIndex: 'cron', key: 'cron', render: (value: string) => value || '—' },
            { title: t('itsm.rule.taskType'), key: 'task', render: (_value: unknown, item: ScheduleItem) => parseAction(item.action).task === 'remind' ? t('itsm.rule.remind') : t('itsm.rule.createTicket') },
            { title: t('itsm.rule.notifyCol'), key: 'notify', render: (_value: unknown, item: ScheduleItem) => parseAction(item.action).notify ? t('itsm.rule.send') : t('itsm.rule.noSend') },
            { title: '下次执行', dataIndex: 'next_run_at', render: (value: string | null) => value ? formatTicketTime(value) : '—' },
            {
              title: t('itsm.admin.enable'),
              dataIndex: 'is_enabled',
              key: 'is_enabled',
              render: (value: boolean, item: ScheduleItem) => (
                <Switch aria-label={`启用${item.name}`} checked={value} disabled={!permissions.can_edit} onChange={(checked) => {
                  void api.updateResource('schedules', item.id, { is_enabled: checked }).then(load).catch((error: Error) => message.error(error.message));
                }} />
              ),
            },
            { fixed: 'right' as const, width: 120,
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: ScheduleItem) => <ItsmRowActions items={[
                { key: 'edit', label: t('itsm.common.edit'), kind: 'edit', hidden: !permissions.can_edit, onClick: () => start(item) },
                { key: 'history', label: '查看执行记录', kind: 'history', onClick: () => setHistory({ id: item.id, name: item.name }) },
                { key: 'delete', label: t('itsm.common.delete'), kind: 'delete', hidden: !permissions.can_delete, danger: true, confirm: { title: t('itsm.rule.deleteSchedule') }, onClick: () => api.deleteResource('schedules', item.id).then(load) },
              ]} />,
            },
          ]}
        />
      </div>
      {history && <ScheduleRunHistory target={history} onClose={() => { setHistory(undefined); void load().catch(() => undefined); }} />}
      <OperateModal formValue={{name,mode,cron,onceAt,task,workflowId,notify,formData}} title={editing ? t('itsm.rule.editSchedule') : t('itsm.rule.newSchedule')} open={open} onCancel={() => setOpen(false)} onOk={save}>
        <div className="flex flex-col gap-3 text-sm">
          <FieldRow label={t('itsm.portal.name')}>
            <Input aria-label="任务名称" maxLength={128} value={name} onChange={(event) => setName(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.rule.mode')}>
            <Radio.Group value={mode} onChange={(event) => setMode(event.target.value)}>
              <Radio value="once">{t('itsm.rule.once')}</Radio>
              <Radio value="cron">{t('itsm.rule.cron')}</Radio>
            </Radio.Group>
          </FieldRow>
          {mode === 'once' ? (
            <FieldRow label={t('itsm.rule.once')}>
              <DatePicker aria-label="执行时间" showTime className="w-full" value={onceAt ? dayjs(onceAt) : null} onChange={(value) => setOnceAt(value ? value.toISOString() : '')} />
            </FieldRow>
          ) : (
            <FieldRow label={t('itsm.rule.period')}>
              <Input aria-label="Cron 表达式" placeholder={t('itsm.rule.cronHint')} value={cron} onChange={(event) => setCron(event.target.value)} />
            </FieldRow>
          )}
          <FieldRow label={t('itsm.rule.taskType')}>
            <Select className="w-full" value={task} options={[{ value: 'create_ticket', label: t('itsm.rule.createTicket') }, { value: 'remind', label: t('itsm.rule.remind') }]} onChange={setTask} />
          </FieldRow>
          {task === 'create_ticket' && <>
            <FieldRow label={t('itsm.ticket.flow')}>
              <Select aria-label="目标流程" showSearch optionFilterProp="label" className="w-full" placeholder={t('itsm.rule.pickWorkflow')} value={workflowId} options={workflows.map((item) => ({ value: item.id, label: item.name }))} onChange={setWorkflowId} />
            </FieldRow>
            <FieldRow label="提单参数" align="start">
              <div className="flex flex-col gap-2">
                <Input.TextArea aria-label="提单参数" rows={4} value={formData} onChange={event => setFormData(event.target.value)} />
                <span className="text-xs text-[var(--color-text-3)]">使用字段标识填写 JSON，例如 {'{"title":"例行巡检","priority":"normal"}'}。需填写目标流程的必填字段，未填写标题时使用任务名称。</span>
              </div>
            </FieldRow>
            <FieldRow label={t('itsm.rule.notifyCol')}>
              <Switch checked={notify} onChange={setNotify} />
            </FieldRow>
          </>}
        </div>
      </OperateModal>
    </div>
  );
}
