'use client';

import { Button, Dropdown, Input, Modal, Radio, Select } from 'antd';
import { useState } from 'react';
import { UserSelector } from './user-selector';
import type { TicketDetail, TicketTaskItem } from '../types';

const LABELS: Record<string, string> = { submit: '提交', approve: '同意', reject: '驳回', claim: '认领', save: '保存', return: '回退', transfer: '转交', withdraw: '撤回', urge: '催办', suspend: '挂起', resume: '恢复', terminate: '终止', close: '关闭', reopen: '重新打开', respond: '响应' };
export interface OperationInput { return_mode?: string; target?: string; opinion?: string }
interface Props {
  ticket: TicketDetail;
  busy: boolean;
  operate: (action: string, task?: TicketTaskItem, extra?: OperationInput) => Promise<boolean>;
}

export function TicketActions({ ticket, busy, operate }: Props) {
  const tasks = ticket.tasks.filter((task) => task.can_operate);
  const [taskId, setTaskId] = useState<number>();
  const task = tasks.find((item) => item.id === taskId) || tasks[0];
  const [action, setAction] = useState('');
  const [target, setTarget] = useState<string[]>([]);
  const [opinion, setOpinion] = useState('');
  const [returnMode, setReturnMode] = useState('previous');
  const taskActions = task?.allowed_actions || [];
  const sideActions = ticket.allowed_actions || [];
  const select = (value: string) => {
    if (['claim', 'save', 'respond', 'resume', 'urge'].includes(value)) {
      void operate(value, taskActions.includes(value) ? task : undefined);
      return;
    }
    setAction(value); setTarget([]); setOpinion(''); setReturnMode('previous');
  };
  const primary = taskActions.includes('approve') ? 'approve' : taskActions.includes('submit') ? 'submit' : '';
  const visible = [...taskActions.filter((value) => ['reject', 'return', 'save'].includes(value)), ...sideActions.filter((value) => value === 'resume')];
  const more = Array.from(new Set([...taskActions, ...sideActions])).filter((value) => value !== primary && !visible.includes(value));
  return <>
    <div className="flex flex-wrap items-center gap-2">
      {tasks.length > 1 ? <Select aria-label="处理任务" value={task?.id} onChange={setTaskId} options={tasks.map((item) => ({ value: item.id, label: item.node_name || item.node_id }))} /> : null}
      {visible.map((value) => <Button key={value} disabled={busy} danger={value === 'reject'} onClick={() => select(value)}>{LABELS[value] || value}</Button>)}
      {more.length ? <Dropdown disabled={busy} menu={{ items: more.map((value) => ({ key: value, label: LABELS[value] || value, danger: ['terminate', 'close'].includes(value), onClick: () => select(value) })) }}><Button disabled={busy}>更多操作</Button></Dropdown> : null}
      {primary ? <Button type="primary" loading={busy} onClick={() => select(primary)}>{LABELS[primary]}</Button> : null}
    </div>
    <Modal title={`${LABELS[action] || ''}工单`} open={Boolean(action)} confirmLoading={busy} okText="确认" cancelText="取消" onCancel={() => { if (!busy) setAction(''); }} okButtonProps={{ disabled: action === 'transfer' && !target.length }} onOk={async () => {
      if (await operate(action, taskActions.includes(action) ? task : undefined, { target: target[0], return_mode: returnMode, opinion })) setAction('');
    }}>
      <div className="flex flex-col gap-4 py-3">
        {taskActions.includes(action) ? <div className="text-sm text-[var(--color-text-3)]">当前步骤：{task?.node_name || task?.node_id}</div> : null}
        {action === 'transfer' ? <UserSelector multiple={false} placeholder="选择接收人" value={target} onChange={setTarget} /> : null}
        {action === 'return' ? <Radio.Group value={returnMode} onChange={(event) => setReturnMode(event.target.value)} options={[{ label: '上一处理节点', value: 'previous' }, { label: '提单节点', value: 'submit' }]} /> : null}
        <Input.TextArea aria-label="处理意见" placeholder="填写处理意见（选填）" value={opinion} maxLength={2000} onChange={(event) => setOpinion(event.target.value)} rows={3} />
      </div>
    </Modal>
  </>;
}
