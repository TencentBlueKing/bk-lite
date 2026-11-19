'use client';

import { Input, InputNumber, Select, Switch, Tag, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { ItsmDrawer } from '@/app/itsm/components/interaction-surfaces';
import { ItsmCreateButton, ItsmListToolbar, ItsmRowActions } from '@/app/itsm/components/list-controls';
import { ItsmListEntry } from '@/app/itsm/components/list-entry';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { UserSelector } from '../../components/user-selector';

interface PolicyDraft {
  name: string;
  workflow_id?: number;
  calendar_id?: number;
  target: string;
  minutes: number;
  warning_minutes: number;
  escalation_users: string[];
  category: string;
  is_enabled: boolean;
}

interface PolicyItem extends PolicyDraft {
  id: number;
  workflow_name: string;
}

interface NamedItem { id: number; name: string }

const CATEGORIES = ['SLA', 'SLO', 'OLA', 'UC'].map(label => ({ value: label.toLowerCase(), label }));
const TARGETS = [{ value: 'response', label: '响应时限' }, { value: 'resolve', label: '解决时限' }];
const EMPTY_DRAFT: PolicyDraft = {
  name: '', category: 'sla', target: 'response', minutes: 60, warning_minutes: 0, escalation_users: [], is_enabled: true,
};

export default function SlaRulePage() {
  const { ready, listSla, listWorkflows, saveSla } = useItsmApi();
  const [keyword, setKeyword] = useState('');
  const [policies, setPolicies] = useState<PolicyItem[]>([]);
  const [calendars, setCalendars] = useState<NamedItem[]>([]);
  const [workflows, setWorkflows] = useState<NamedItem[]>([]);
  const [canEdit, setCanEdit] = useState(false);
  const [draft, setDraft] = useState<PolicyDraft>();
  const [editingId, setEditingId] = useState<number>();
  const load = useCallback(async () => {
    const result = await listSla() as { policies: PolicyItem[]; calendars: NamedItem[]; can_edit: boolean };
    setPolicies(result.policies);
    setCalendars(result.calendars);
    setCanEdit(result.can_edit);
  }, [listSla]);

  useEffect(() => {
    if (ready) void load().catch((error: Error) => message.error(error.message));
  }, [ready, load]);

  const open = Boolean(draft);
  useEffect(() => {
    if (!open) return;
    let active = true;
    void listWorkflows().then(result => {
      if (active) setWorkflows((result as { items: NamedItem[] }).items);
    }).catch((error: Error) => { if (active) message.error(error.message); });
    return () => { active = false; };
  }, [open, listWorkflows]);

  const edit = (item?: PolicyItem) => {
    setEditingId(item?.id);
    setDraft(item || EMPTY_DRAFT);
  };
  const change = (values: Partial<PolicyDraft>) => setDraft(current => current ? { ...current, ...values } : current);

  const save = async () => {
    if (!draft) return;
    if (!draft.name.trim() || !draft.workflow_id || !draft.calendar_id) throw new Error('请填写策略名称，选择流程和服务窗口');
    if (draft.warning_minutes >= draft.minutes) throw new Error('预警提前量必须小于时限');
    await saveSla({ ...draft, kind: 'policy', policy_id: editingId, name: draft.name.trim() });
    setDraft(undefined);
    await load();
  };

  return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    <ItsmListToolbar search={{ value: keyword, onChange: setKeyword, placeholder: '搜索策略或流程' }}
      actions={canEdit ? <ItsmCreateButton onClick={() => edit()} /> : null} />
    <CustomTable queryKey={keyword} rowKey="id"
      dataSource={policies.filter(item => `${item.name} ${item.workflow_name} ${item.category}`.toLowerCase().includes(keyword.trim().toLowerCase()))}
      locale={{ emptyText: '暂无 SLA 策略' }}
      columns={[
        { title: '名称', dataIndex: 'name', key: 'name', render: (name: string, item: PolicyItem) => <ItsmListEntry allowed={canEdit} onClick={() => edit(item)}>{name}</ItsmListEntry> },
        { title: '流程', dataIndex: 'workflow_name', key: 'workflow', render: (value: string) => value || '未绑定' },
        { title: '类别', dataIndex: 'category', key: 'category', render: (value: string) => value.toUpperCase() },
        { title: '计时目标', dataIndex: 'target', key: 'target', render: (value: string) => TARGETS.find(item => item.value === value)?.label },
        { title: '时限', dataIndex: 'minutes', key: 'minutes', render: (value: number) => `${value} 分钟` },
        { title: '预警', dataIndex: 'warning_minutes', key: 'warning', render: (value: number) => value ? `提前 ${value} 分钟` : '—' },
        { title: '超时升级', dataIndex: 'escalation_users', key: 'escalation', render: (value: string[]) => value.length ? `${value.length} 人` : '—' },
        { title: '状态', dataIndex: 'is_enabled', key: 'enabled', render: (value: boolean, item: PolicyItem) => canEdit && item.workflow_id
          ? <Switch aria-label={`启用${item.name}`} checked={value} onChange={checked => {
            void saveSla({ policy_id: item.id, is_enabled: checked }).then(load).catch((error: Error) => message.error(error.message));
          }} />
          : <Tag color={item.workflow_id && value ? 'success' : 'default'}>{item.workflow_id && value ? '已启用' : '未启用'}</Tag> },
        ...(canEdit ? [{ title: '操作', key: 'actions', width: 80, render: (_value: unknown, item: PolicyItem) => <ItsmRowActions items={[
          { key: 'edit', kind: 'edit', label: '编辑策略', onClick: () => edit(item) },
        ]} /> }] : []),
      ]} />
    {draft && <ItsmDrawer open title={editingId ? '编辑 SLA 策略' : '新建 SLA 策略'} formValue={draft}
      onCancel={() => setDraft(undefined)} onOk={save}>
      <div className="flex flex-col gap-4">
        <FieldRow label="策略名称"><Input aria-label="策略名称" maxLength={128} value={draft.name} onChange={e => change({ name: e.target.value })} /></FieldRow>
        <FieldRow label="适用流程"><Select aria-label="适用流程" className="w-full" showSearch optionFilterProp="label" value={draft.workflow_id} options={workflows.map(item => ({ value: item.id, label: item.name }))} onChange={workflow_id => change({ workflow_id })} /></FieldRow>
        <FieldRow label="策略类别"><Select aria-label="策略类别" className="w-full" value={draft.category} options={CATEGORIES} onChange={category => change({ category })} /></FieldRow>
        <FieldRow label="计时目标"><Select aria-label="计时目标" className="w-full" value={draft.target} options={TARGETS} onChange={target => change({ target })} /></FieldRow>
        <FieldRow label="服务窗口"><Select aria-label="服务窗口" className="w-full" showSearch optionFilterProp="label" value={draft.calendar_id} options={calendars.map(item => ({ value: item.id, label: item.name }))} onChange={calendar_id => change({ calendar_id })} /></FieldRow>
        <FieldRow label="时限（分钟）"><InputNumber aria-label="时限（分钟）" className="w-full" min={1} max={525600} precision={0} value={draft.minutes} onChange={value => change({ minutes: value ?? 1 })} /></FieldRow>
        <FieldRow label="提前预警（分钟）" align="start">
          <div className="flex flex-col gap-2">
            <InputNumber aria-label="提前预警（分钟）" className="w-full" min={0} precision={0} value={draft.warning_minutes} onChange={value => change({ warning_minutes: value ?? 0 })} />
            <span className="text-xs text-[var(--color-text-3)]">按服务窗口提前通知当前处理人，填 0 关闭预警。</span>
          </div>
        </FieldRow>
        <FieldRow label="超时升级对象" align="start">
          <div className="flex flex-col gap-2">
            <UserSelector ariaLabel="超时升级对象" allowClear value={draft.escalation_users} onChange={escalation_users => change({ escalation_users })} />
            <span className="text-xs text-[var(--color-text-3)]">超时后向所选人员发送站内通知，最多 20 人。留空时只标记超时。</span>
          </div>
        </FieldRow>
        <FieldRow label="启用策略"><Switch aria-label="启用策略" checked={draft.is_enabled} onChange={is_enabled => change({ is_enabled })} /></FieldRow>
        <p className="text-xs text-[var(--color-text-3)]">策略变更适用于新建工单。已有工单按开始计时时的策略执行。</p>
      </div>
    </ItsmDrawer>}
  </div>;
}
