'use client';

import { Button, Dropdown, Input, Select } from 'antd';
import dayjs from 'dayjs';
import { useId, useState } from 'react';
import { ItsmModal as Modal } from '@/app/itsm/components/interaction-surfaces';
import { displayActionLabel, ticketActionLabel } from '../constants/node-catalog';
import { UserSelector } from './user-selector';
import type { TicketDetail, TicketTaskItem } from '../types';

const IMMEDIATE_ACTIONS = new Set(['claim', 'save', 'respond', 'resume', 'urge']);
const DANGER_ACTIONS = new Set(['reject', 'terminate', 'close']);

export interface OperationInput {
  return_node_id?: string;
  target?: string;
  opinion?: string;
}

interface Props {
  ticket: TicketDetail;
  busy: boolean;
  onTaskChange?: (taskId: number) => void;
  operate: (action: string, task?: TicketTaskItem, extra?: OperationInput) => Promise<boolean>;
}

interface PendingOperation {
  action: string;
  label: string;
  ticketId: number;
  taskId?: number;
}

export function TicketActions({ ticket, busy, operate, onTaskChange }: Props) {
  const tasks = ticket.tasks.filter(task => task.can_operate);
  const [taskId, setTaskId] = useState<number>();
  const task = tasks.find(item => item.id === (onTaskChange ? ticket.selected_task_id : taskId)) || tasks[0];
  const [pending, setPending] = useState<PendingOperation>();
  const [target, setTarget] = useState<string[]>([]);
  const [opinion, setOpinion] = useState('');
  const [returnTarget, setReturnTarget] = useState<string>();
  const recipientInputId = useId();
  const returnTargetId = useId();
  const opinionInputId = useId();

  const taskActions = (task?.allowed_actions ?? []).filter(action => action !== 'return' || task?.return_targets?.length);
  const sideActions = ticket.allowed_actions ?? [];
  const action = pending?.action ?? '';
  const confirmationTask = tasks.find(item => item.id === pending?.taskId && item.allowed_actions?.includes(action));
  const opinionActions = pending?.taskId === undefined ? ticket.required_opinion_actions : confirmationTask?.required_opinion_actions;
  const requiresOpinion = opinionActions?.includes(action) ?? false;
  const returnOptions = (confirmationTask?.return_targets ?? []).map(candidate => ({
    value: candidate.node_id,
    label: candidate.name,
    completedAt: candidate.completed_at,
  }));
  const canOperate = pending?.ticketId === ticket.id && (pending.taskId === undefined ? sideActions.includes(action) : Boolean(confirmationTask));
  const canConfirm = canOperate
    && (!requiresOpinion || Boolean(opinion.trim()))
    && (action !== 'transfer' || target.length > 0)
    && (action !== 'return' || returnOptions.some(option => option.value === returnTarget));

  const select = (value: string, label: string) => {
    const selectedTask = taskActions.includes(value) ? task : undefined;
    const requiredActions = selectedTask ? selectedTask.required_opinion_actions : ticket.required_opinion_actions;
    if (IMMEDIATE_ACTIONS.has(value) && !requiredActions?.includes(value)) {
      void operate(value, selectedTask);
      return;
    }
    setPending({ action: value, label, ticketId: ticket.id, taskId: selectedTask?.id });
    setTarget([]);
    setOpinion('');
    setReturnTarget(undefined);
  };

  const primary = taskActions.includes('approve') ? 'approve' : taskActions.includes('submit') ? 'submit' : '';
  const available = new Set([...taskActions, ...sideActions]);
  const configured = ((task ? task.action_display : ticket.action_display) ?? []).filter(row => available.has(row.action));
  const configuredActions = new Set(configured.map(row => row.action));
  const visible = [...taskActions.filter(value => ['reject', 'return', 'save'].includes(value)), ...sideActions.filter(value => value === 'resume')]
    .filter(value => !configuredActions.has(value));
  const more = [...available].filter(value => !configuredActions.has(value) && value !== primary && !visible.includes(value));
  const renderButton = (value: string, label = ticketActionLabel(value)) => (
    <Button key={value} type={value === primary ? 'primary' : 'default'} danger={DANGER_ACTIONS.has(value)}
      loading={value === primary && busy} disabled={busy} onClick={() => select(value, label)}>{label}</Button>
  );

  return <>
    <div role="group" aria-label="工单操作" className="flex flex-wrap items-center gap-2">
      {tasks.length > 1 ? <Select aria-label="处理任务" value={task?.id} disabled={busy} onChange={onTaskChange || setTaskId} options={tasks.map(item => ({ value: item.id, label: item.node_name || item.node_id }))} /> : null}
      {configured.map(row => renderButton(row.action, displayActionLabel(row, ticketActionLabel)))}
      {visible.map(value => renderButton(value))}
      {more.length ? <Dropdown disabled={busy} menu={{ items: more.map(value => ({ key: value, label: ticketActionLabel(value), danger: DANGER_ACTIONS.has(value), onClick: () => select(value, ticketActionLabel(value)) })) }}><Button disabled={busy}>更多操作</Button></Dropdown> : null}
      {primary && !configuredActions.has(primary) ? renderButton(primary) : null}
    </div>
    <Modal formValue={{ target, opinion, returnTarget }} title={`${pending?.label || ''}工单`} open={Boolean(pending)}
      confirmLoading={busy} okText={`确认${pending?.label || '操作'}`} cancelText="取消"
      onCancel={() => setPending(undefined)} okButtonProps={{ disabled: !canConfirm }}
      onOk={async () => {
        if (!canConfirm) return;
        const success = await operate(action, confirmationTask, {
          opinion: opinion.trim(),
          ...(action === 'transfer' ? { target: target[0] } : {}),
          ...(action === 'return' ? { return_node_id: returnTarget } : {}),
        });
        if (success) setPending(undefined);
      }}>
      <div className="flex flex-col gap-4 py-3">
        {pending && !canOperate && <span role="alert">当前操作已不可用，请刷新工单。</span>}
        {pending && pending.label !== ticketActionLabel(action) && <div className="text-sm text-[var(--color-text-3)]">操作类型：{ticketActionLabel(action)}</div>}
        {canOperate && confirmationTask && <div className="text-sm text-[var(--color-text-3)]">当前步骤：{confirmationTask.node_name || confirmationTask.node_id}</div>}
        {canOperate && action === 'transfer' && confirmationTask && <div className="flex flex-col gap-2">
          <label htmlFor={recipientInputId}>接收人</label>
          <UserSelector key={`${ticket.id}:${confirmationTask.id}`} id={recipientInputId} ariaLabel="接收人"
            multiple={false} placeholder="选择接收人" allowClear value={target} onChange={setTarget}
            transfer={{ ticketId: ticket.id, taskId: confirmationTask.id }} />
        </div>}
        {canOperate && action === 'return' && <div className="flex flex-col gap-2">
          <label htmlFor={returnTargetId}>回退节点</label>
          <Select id={returnTargetId} aria-label="回退节点" aria-required showSearch optionFilterProp="label"
            placeholder="选择已完成的历史节点" notFoundContent="没有可回退的历史节点"
            value={returnOptions.some(option => option.value === returnTarget) ? returnTarget : undefined}
            options={returnOptions} onChange={setReturnTarget}
            optionRender={({ data }) => <div className="flex items-center justify-between gap-3">
              <span>{data.label}</span>
              <time className="text-xs text-[var(--color-text-3)]" dateTime={data.completedAt}>
                {dayjs(data.completedAt).format('YYYY-MM-DD HH:mm')}
              </time>
            </div>} />
        </div>}
        <div className="flex flex-col gap-2">
          <label htmlFor={opinionInputId}>处理意见{requiresOpinion && <span className="text-[var(--color-text-3)]">（必填）</span>}</label>
          <Input.TextArea id={opinionInputId} aria-label="处理意见" required={requiresOpinion} disabled={!canOperate}
            placeholder={requiresOpinion ? '填写处理意见' : '填写处理意见（选填）'} value={opinion} maxLength={2000}
            onChange={event => setOpinion(event.target.value)} rows={3} />
        </div>
      </div>
    </Modal>
  </>;
}
